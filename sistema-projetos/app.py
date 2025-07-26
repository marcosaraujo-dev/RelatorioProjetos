import os
import sys
import webbrowser
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_file
import pandas as pd
import plotly
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
import json
from database import DatabaseManager
import tempfile
import logging
import getpass
import socket
import platform

# Configurar logging para capturar tudo
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = 'sistema_projetos_empresa_2025_web_key'

def get_user_info():
    """Captura informações completas do usuário do sistema"""
    try:
        # Informações básicas
        username = getpass.getuser()
        hostname = socket.gethostname()
        system = platform.system()
        
        # Informações de domínio (para ambiente corporativo)
        domain = os.environ.get('USERDOMAIN', 'Local')
        computer_name = os.environ.get('COMPUTERNAME', hostname)
        
        # Formatar nome para exibição
        display_name = username.replace('.', ' ').title()
        if len(display_name) > 20:
            display_name = display_name[:18] + "..."
        
        # Determinar tipo de usuário
        is_domain_user = domain and domain != hostname and domain.upper() != 'LOCAL'
        user_type = "Usuário de Domínio" if is_domain_user else "Usuário Local"
        
        return {
            'name': display_name,
            'username': username,
            'hostname': hostname,
            'computer_name': computer_name,
            'domain': domain,
            'system': f"{system} {platform.release()}",
            'is_domain_user': is_domain_user,
            'user_type': user_type,
            'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'icon': 'fas fa-user-circle' if is_domain_user else 'fas fa-user'
        }
    except Exception as e:
        log_message(f"Erro ao capturar informações do usuário: {e}")
        return {
            'name': 'Sistema Interno',
            'username': 'sistema',
            'hostname': 'Local',
            'computer_name': 'Local',
            'domain': 'Local',
            'system': 'Sistema Local',
            'is_domain_user': False,
            'user_type': 'Sistema',
            'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'icon': 'fas fa-cog'
        }

@app.context_processor
def inject_user_info():
    """Injeta informações do usuário em todos os templates"""
    return {'current_user': get_user_info()}

# Inicializar o gerenciador de banco
db_manager = DatabaseManager()

# Lista global para armazenar logs
app_logs = []

def log_message(message):
    """Adicionar mensagem aos logs da aplicação"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    app_logs.append(log_entry)
    print(log_entry)
    
    # Manter apenas os últimos 100 logs
    if len(app_logs) > 100:
        app_logs.pop(0)

# Context processor para disponibilizar em todos os templates
@app.context_processor
def inject_user_info():
    """Injeta informações do usuário em todos os templates"""
    return {'current_user': get_user_info()}        

def convert_numpy_types(obj):
    """Converter tipos numpy para tipos Python nativos para serialização JSON"""
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif pd.isna(obj):
        return 0  # Converter NaN para 0
    elif hasattr(obj, 'item'):  # numpy types
        return obj.item()
    elif hasattr(obj, 'tolist'):  # numpy arrays
        return obj.tolist()
    else:
        return obj        

# ===============================
# ROTAS DO DASHBOARD
# ===============================

@app.route('/')
def index():
    """Página principal com dashboard melhorado"""
    default_stats = {
        'total_epicos': 0,
        'epicos_concluidos': 0,
        'epicos_em_andamento': 0,
        'epicos_atrasados': 0,
        'epicos_proximo_prazo': 0,  # NOVO
        'epicos_baixo_progresso': 0,  # NOVO
        'total_subtasks': 0,
        'percentual_medio': 0.0,
        'error': None
    }
    
    default_equipes = []
    
    try:
        success, message = db_manager.test_connection()
        if not success:
            default_stats['error'] = f"Erro de conexão: {message}"
            return render_template('dashboard.html', stats=default_stats, equipes=default_equipes)
        
        conn = db_manager.get_connection()
        
        # Estatísticas dos épicos
        query_stats = """
        SELECT 
            COUNT(*) as total_epicos,
            SUM(CASE WHEN EpicStatus = 'Done' THEN 1 ELSE 0 END) as epicos_concluidos,
            SUM(CASE WHEN EpicStatus IN ('In Progress', 'Development', 'In Review') THEN 1 ELSE 0 END) as epicos_em_andamento,
            SUM(CASE WHEN EpicDueDate < GETDATE() AND EpicStatus NOT IN ('Done', 'Closed') THEN 1 ELSE 0 END) as epicos_atrasados,
            AVG(CAST(ISNULL(TasksPercentualMedia, 0) as float)) as percentual_medio
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicInicioPlanejado IS NOT NULL
        And TipoRegistroCalculo = 'Planejado Time'
        """
        
        df_stats = pd.read_sql(query_stats, conn)
        if not df_stats.empty:
            stats = convert_numpy_types(df_stats.iloc[0].to_dict())
            for key in default_stats:
                if key not in stats or stats[key] is None:
                    stats[key] = default_stats[key]
        else:
            stats = default_stats
        
        # Adicionar contagens de alertas específicos
        # Épicos que vencem nos próximos 7 dias
        query_proximo = """
        SELECT COUNT(*) as count_proximo
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicInicioPlanejado IS NOT NULL
        And TipoRegistroCalculo = 'Planejado Time'
        AND EpicDueDate BETWEEN GETDATE() AND DATEADD(day, 7, GETDATE())
        AND EpicStatus NOT IN ('Done', 'Closed')
        """
        
        df_proximo = pd.read_sql(query_proximo, conn)
        if not df_proximo.empty:
            stats['epicos_proximo_prazo'] = convert_numpy_types(df_proximo.iloc[0]['count_proximo'])
        
        # Épicos com baixo progresso
        query_baixo = """
        SELECT COUNT(*) as count_baixo
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicInicioPlanejado IS NOT NULL
        And TipoRegistroCalculo = 'Planejado Time'
        AND CAST(ISNULL(TasksPercentualMedia, 0) as decimal(5,2)) < 30
        AND EpicInicioPlanejado < DATEADD(day, -15, GETDATE())
        AND EpicStatus NOT IN ('Done', 'Closed')
        """
        
        df_baixo = pd.read_sql(query_baixo, conn)
        if not df_baixo.empty:
            stats['epicos_baixo_progresso'] = convert_numpy_types(df_baixo.iloc[0]['count_baixo'])
        
        # Contagem de subtasks
        query_subtasks = "SELECT COUNT(*) as total_subtasks FROM BI_Jira_SubTasks_Datas_Grafico"
        df_subtasks = pd.read_sql(query_subtasks, conn)
        if not df_subtasks.empty:
            stats['total_subtasks'] = convert_numpy_types(df_subtasks.iloc[0]['total_subtasks'])
        
        # Épicos por equipe
        query_equipes = """
        SELECT 
            ISNULL(EpicEquipe, 'Sem Equipe') as EpicEquipe,
            COUNT(*) as quantidade,
            AVG(CAST(ISNULL(TasksPercentualMedia, 0) as float)) as percentual_medio,
            SUM(CASE WHEN EpicStatus = 'Done' THEN 1 ELSE 0 END) as concluidos,
            SUM(CASE WHEN EpicDueDate < GETDATE() AND EpicStatus NOT IN ('Done', 'Closed') THEN 1 ELSE 0 END) as atrasados
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicInicioPlanejado IS NOT NULL
        And TipoRegistroCalculo = 'Planejado Time'
        GROUP BY EpicEquipe
        ORDER BY quantidade DESC
        """
        
        df_equipes = pd.read_sql(query_equipes, conn)
        equipes = convert_numpy_types(df_equipes.to_dict('records')) if not df_equipes.empty else default_equipes
        
        conn.close()
        return render_template('dashboard.html', stats=stats, equipes=equipes)
    
    except Exception as e:
        print(f"Erro no dashboard: {str(e)}")
        default_stats['error'] = str(e)
        return render_template('dashboard.html', stats=default_stats, equipes=default_equipes)

@app.route('/api/dashboard-data')
def dashboard_data():
    """API para dados do dashboard com filtros e contagens de alertas"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        status_filter = request.args.get('status', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        
        
        # Construir filtros de data baseado no período
      #  today = datetime.now()
      #  if periodo_filter == 'ano_atual':
      #      data_inicio = f"{today.year}-01-01"
      #      data_fim = f"{today.year}-12-31"
      #  elif periodo_filter == '6_meses':
      #      data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
      #      data_fim = today.strftime('%Y-%m-%d')
      #  elif periodo_filter == '3_meses':
      #      data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
      #      data_fim = today.strftime('%Y-%m-%d')
      #  elif periodo_filter == 'mes_atual':
      #      data_inicio = f"{today.year}-{today.month:02d}-01"
      #      data_fim = today.strftime('%Y-%m-%d')
      #  else:  # todos
      #      data_inicio = None
      #      data_fim = None
        
        data_inicio, data_fim = calculate_period_dates(periodo_filter)
         
        # Query base com filtros
        where_conditions = ["EpicInicioPlanejado IS NOT NULL"]
        params = []
        
        if equipe_filter:
            where_conditions.append("ISNULL(EpicEquipe, '') = ?")
            params.append(equipe_filter)
        
        if produto_filter:
            where_conditions.append("ISNULL(EpicProduto, '') = ?")
            params.append(produto_filter)
        
        if status_filter:
            where_conditions.append("ISNULL(EpicStatus, '') = ?")
            params.append(status_filter)
        
        if data_inicio and data_fim:
            where_conditions.append("""(
                (EpicDueDate >= ? AND EpicDueDate <= ?) OR
                (EpicInicioPlanejado >= ? AND EpicInicioPlanejado <= ?) OR
                (EpicInicioPlanejado < ? AND EpicDueDate > ?)
            )""")
            params.extend([data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim])
        
        where_clause = " AND ".join(where_conditions)
        
        # Estatísticas filtradas
        query_stats = f"""
        SELECT 
            COUNT(*) as total_epicos,
            SUM(CASE WHEN EpicStatus = 'Done' THEN 1 ELSE 0 END) as epicos_concluidos,
            SUM(CASE WHEN EpicStatus IN ('In Progress', 'Development', 'In Review') THEN 1 ELSE 0 END) as epicos_em_andamento,
            SUM(CASE WHEN EpicDueDate < GETDATE() AND EpicStatus NOT IN ('Done', 'Closed') THEN 1 ELSE 0 END) as epicos_atrasados,
            AVG(CAST(ISNULL(TasksPercentualMedia, 0) as float)) as percentual_medio
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        """
        
        df_stats = pd.read_sql(query_stats, conn, params=params)
        stats = convert_numpy_types(df_stats.iloc[0].to_dict()) if not df_stats.empty else {}
        
        # Adicionar contagens específicas para alertas
        # Épicos que vencem nos próximos 7 dias
        query_proximo_prazo = f"""
        SELECT COUNT(*) as count_proximo_prazo
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        AND EpicDueDate BETWEEN GETDATE() AND DATEADD(day, 7, GETDATE())
        AND EpicStatus NOT IN ('Done', 'Closed')
        """
        
        df_proximo = pd.read_sql(query_proximo_prazo, conn, params=params)
        stats['epicos_proximo_prazo'] = convert_numpy_types(df_proximo.iloc[0]['count_proximo_prazo']) if not df_proximo.empty else 0
        
        # Épicos com baixo progresso
        query_baixo_progresso = f"""
        SELECT COUNT(*) as count_baixo_progresso
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        AND CAST(ISNULL(TasksPercentualMedia, 0) as decimal(5,2)) < 30
        AND EpicInicioPlanejado < DATEADD(day, -15, GETDATE())
        AND EpicStatus NOT IN ('Done', 'Closed')
        """
        
        df_baixo = pd.read_sql(query_baixo_progresso, conn, params=params)
        stats['epicos_baixo_progresso'] = convert_numpy_types(df_baixo.iloc[0]['count_baixo_progresso']) if not df_baixo.empty else 0
        
        # Dados por equipe filtrados
        query_equipes = f"""
        SELECT 
            ISNULL(EpicEquipe, 'Sem Equipe') as EpicEquipe,
            COUNT(*) as quantidade,
            AVG(CAST(ISNULL(TasksPercentualMedia, 0) as float)) as percentual_medio,
            SUM(CASE WHEN EpicStatus = 'Done' THEN 1 ELSE 0 END) as concluidos,
            SUM(CASE WHEN EpicDueDate < GETDATE() AND EpicStatus NOT IN ('Done', 'Closed') THEN 1 ELSE 0 END) as atrasados
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        GROUP BY EpicEquipe
        ORDER BY quantidade DESC
        """
        
        df_equipes = pd.read_sql(query_equipes, conn, params=params)
        equipes = convert_numpy_types(df_equipes.to_dict('records')) if not df_equipes.empty else []
        
        # Buscar dados para distribuição de status
        query_status_dist = f"""
        SELECT 
            ISNULL(EpicStatus, 'Indefinido') as status,
            COUNT(*) as quantidade
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        GROUP BY EpicStatus
        ORDER BY quantidade DESC
        """
        
        df_status_dist = pd.read_sql(query_status_dist, conn, params=params)
        status_distribution = convert_numpy_types(df_status_dist.to_dict('records')) if not df_status_dist.empty else []
        
        # Estatísticas para o período atual 
        epicos_atual = stats.get('total_epicos', 0)

        # Buscar total do período anterior (ex: mês anterior)
        if periodo_filter == 'mes_atual':
            mes_anterior_inicio = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            mes_anterior_fim = today.replace(day=1) - timedelta(days=1)
            
            query_anterior = """
            SELECT COUNT(*) as total_epicos
            FROM BI_Jira_Epico_Datas_Grafico
            WHERE EpicInicioPlanejado IS NOT NULL
            AND EpicInicioPlanejado >= ?
            AND EpicInicioPlanejado <= ?
            """
            df_ant = pd.read_sql(query_anterior, conn, params=[mes_anterior_inicio, mes_anterior_fim])
            
            if not df_ant.empty:
                epicos_anterior = convert_numpy_types(df_ant.iloc[0]['total_epicos'])
                if epicos_anterior > 0:
                    tendencia = round(((epicos_atual - epicos_anterior) / epicos_anterior) * 100, 1)
                    stats['tendencia_epicos'] = tendencia
                else:
                    stats['tendencia_epicos'] = None

        # Query do Timeline
        log_message("Buscando dados do timeline...")
        
        query_timeline = f"""
        SELECT 
            FORMAT(EpicInicioPlanejado, 'yyyy-MM') as Mes,
            COUNT(*) as Total,
            SUM(CASE WHEN EpicStatus IN ('Done', 'Closed', 'Concluído') THEN 1 ELSE 0 END) as Realizados
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        GROUP BY FORMAT(EpicInicioPlanejado, 'yyyy-MM')
        ORDER BY FORMAT(EpicInicioPlanejado, 'yyyy-MM')
        """

        log_message(f"Query timeline: {query_timeline}")
        log_message(f"Params timeline: {params}")
        
        df_timeline = pd.read_sql(query_timeline, conn, params=params)
        
        log_message(f"Timeline result: {len(df_timeline)} rows")
        if not df_timeline.empty:
            log_message(f"Timeline data: {df_timeline.head()}")

        # Monta os arrays para o frontend
        if not df_timeline.empty:
            timeline_data = {
                'meses': df_timeline['Mes'].tolist(),
                'planejado': df_timeline['Total'].astype(int).tolist(),
                'realizado': df_timeline['Realizados'].astype(int).tolist()
            }
            log_message(f"Timeline data criado: {timeline_data}")
        else:
            log_message("Timeline vazio - usando dados padrão")
            timeline_data = {
                'meses': [],
                'planejado': [],
                'realizado': []
            }
        
        #  Adicionar informação do período para o frontend
        periodo_info = {
            'periodo_selecionado': periodo_filter,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'descricao': get_periodo_description(periodo_filter)
        }
        
        conn.close()
        
        # Total de entregas (mesmo que total de épicos concluídos)
        stats['total_entregas'] = stats.get('epicos_concluidos', 0)
        
        response_data = {
            'stats': stats,
            'equipes': equipes,
            'status_distribution': status_distribution,
            'periodo_info': periodo_info,
            'timeline': timeline_data,  # IMPORTANTE: Incluir timeline na resposta
            'filtros_aplicados': {
                'equipe': equipe_filter,
                'produto': produto_filter,
                'status': status_filter,
                'periodo': periodo_filter
            }
        }
        
        log_message(f"Retornando dados com timeline: {response_data.get('timeline', {})}")
        
        return jsonify(response_data)
        
    except Exception as e:
        log_message(f"Erro no dashboard_data: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/api/dashboard-filters')
def dashboard_filters():
    """API para obter opções de filtros do dashboard"""
    try:
        conn = db_manager.get_connection()
        
        # Buscar equipes distintas
        query_equipes = """
        SELECT DISTINCT ISNULL(EpicEquipe, 'Sem Equipe') as equipe
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicEquipe IS NOT NULL AND EpicEquipe != ''
        ORDER BY equipe
        """
        df_equipes = pd.read_sql(query_equipes, conn)
        equipes = df_equipes['equipe'].tolist() if not df_equipes.empty else []
        
        # Buscar produtos distintos
        query_produtos = """
        SELECT DISTINCT ISNULL(EpicProduto, 'Sem Produto') as produto
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicProduto IS NOT NULL AND EpicProduto != ''
        ORDER BY produto
        """
        df_produtos = pd.read_sql(query_produtos, conn)
        produtos = df_produtos['produto'].tolist() if not df_produtos.empty else []
        
        # Buscar status distintos
        query_status = """
        SELECT DISTINCT ISNULL(EpicStatus, 'Indefinido') as status
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicStatus IS NOT NULL AND EpicStatus != ''
        ORDER BY status
        """
        df_status = pd.read_sql(query_status, conn)
        status = df_status['status'].tolist() if not df_status.empty else []
        
        conn.close()
        
        return jsonify({
            'equipes': equipes,
            'produtos': produtos,
            'status': status
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

def dashboard_data():
    """API para dados do dashboard com filtros e contagens de alertas"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        status_filter = request.args.get('status', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        
        # Construir filtros de data baseado no período
        today = datetime.now()
        if periodo_filter == 'ano_atual':
            data_inicio = f"{today.year}-01-01"
            data_fim = f"{today.year}-12-31"
        elif periodo_filter == '6_meses':
            data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == '3_meses':
            data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == 'mes_atual':
            data_inicio = f"{today.year}-{today.month:02d}-01"
            data_fim = today.strftime('%Y-%m-%d')
        else:  # todos
            data_inicio = None
            data_fim = None
        
        # Query base com filtros
        where_conditions = ["EpicInicioPlanejado IS NOT NULL"]
        params = []
        
        if equipe_filter:
            where_conditions.append("ISNULL(EpicEquipe, '') = ?")
            params.append(equipe_filter)
        
        if produto_filter:
            where_conditions.append("ISNULL(EpicProduto, '') = ?")
            params.append(produto_filter)
        
        if status_filter:
            where_conditions.append("ISNULL(EpicStatus, '') = ?")
            params.append(status_filter)
        
        if data_inicio and data_fim:
            where_conditions.append("""(
                (EpicDueDate >= ? AND EpicDueDate <= ?) OR
                (EpicInicioPlanejado >= ? AND EpicInicioPlanejado <= ?) OR
                (EpicInicioPlanejado < ? AND EpicDueDate > ?)
            )""")
            params.extend([data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim])
        
        where_clause = " AND ".join(where_conditions)
        
        # Estatísticas filtradas
        query_stats = f"""
        SELECT 
            COUNT(*) as total_epicos,
            SUM(CASE WHEN EpicStatus = 'Done' THEN 1 ELSE 0 END) as epicos_concluidos,
            SUM(CASE WHEN EpicStatus IN ('In Progress', 'Development', 'In Review') THEN 1 ELSE 0 END) as epicos_em_andamento,
            SUM(CASE WHEN EpicDueDate < GETDATE() AND EpicStatus NOT IN ('Done', 'Closed') THEN 1 ELSE 0 END) as epicos_atrasados,
            AVG(CAST(ISNULL(TasksPercentualMedia, 0) as float)) as percentual_medio
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        """
        
        df_stats = pd.read_sql(query_stats, conn, params=params)
        stats = convert_numpy_types(df_stats.iloc[0].to_dict()) if not df_stats.empty else {}
        
        # Adicionar contagens específicas para alertas
        # Épicos que vencem nos próximos 7 dias
        query_proximo_prazo = f"""
        SELECT COUNT(*) as count_proximo_prazo
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        AND EpicDueDate BETWEEN GETDATE() AND DATEADD(day, 7, GETDATE())
        AND EpicStatus NOT IN ('Done', 'Closed')
        """
        
        df_proximo = pd.read_sql(query_proximo_prazo, conn, params=params)
        stats['epicos_proximo_prazo'] = convert_numpy_types(df_proximo.iloc[0]['count_proximo_prazo']) if not df_proximo.empty else 0
        
        # Épicos com baixo progresso
        query_baixo_progresso = f"""
        SELECT COUNT(*) as count_baixo_progresso
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        AND CAST(ISNULL(TasksPercentualMedia, 0) as decimal(5,2)) < 30
        AND EpicInicioPlanejado < DATEADD(day, -15, GETDATE())
        AND EpicStatus NOT IN ('Done', 'Closed')
        """
        
        df_baixo = pd.read_sql(query_baixo_progresso, conn, params=params)
        stats['epicos_baixo_progresso'] = convert_numpy_types(df_baixo.iloc[0]['count_baixo_progresso']) if not df_baixo.empty else 0
        
        # Dados por equipe filtrados
        query_equipes = f"""
        SELECT 
            ISNULL(EpicEquipe, 'Sem Equipe') as EpicEquipe,
            COUNT(*) as quantidade,
            AVG(CAST(ISNULL(TasksPercentualMedia, 0) as float)) as percentual_medio,
            SUM(CASE WHEN EpicStatus = 'Done' THEN 1 ELSE 0 END) as concluidos,
            SUM(CASE WHEN EpicDueDate < GETDATE() AND EpicStatus NOT IN ('Done', 'Closed') THEN 1 ELSE 0 END) as atrasados
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        GROUP BY EpicEquipe
        ORDER BY quantidade DESC
        """
        
        df_equipes = pd.read_sql(query_equipes, conn, params=params)
        equipes = convert_numpy_types(df_equipes.to_dict('records')) if not df_equipes.empty else []
        
        # Buscar dados para distribuição de status
        query_status_dist = f"""
        SELECT 
            ISNULL(EpicStatus, 'Indefinido') as status,
            COUNT(*) as quantidade
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE {where_clause}
        GROUP BY EpicStatus
        ORDER BY quantidade DESC
        """
        
        df_status_dist = pd.read_sql(query_status_dist, conn, params=params)
        status_distribution = convert_numpy_types(df_status_dist.to_dict('records')) if not df_status_dist.empty else []
        
        # Calculando tendência de épicos (vs período anterior)
        epicos_atual = stats.get('total_epicos', 0)
        epicos_anterior = 0
        tendencia = None

        # Calcular período anterior (apenas se houver filtro de tempo)
        if data_inicio and data_fim:
            dt_inicio_anterior = (datetime.strptime(data_inicio, '%Y-%m-%d') - (datetime.strptime(data_fim, '%Y-%m-%d') - datetime.strptime(data_inicio, '%Y-%m-%d'))).strftime('%Y-%m-%d')
            dt_fim_anterior = (datetime.strptime(data_inicio, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

            query_anterior = f"""
            SELECT COUNT(*) as total_epicos
            FROM BI_Jira_Epico_Datas_Grafico
            WHERE EpicInicioPlanejado IS NOT NULL
            AND (
                (EpicInicioPlanejado BETWEEN ? AND ?) OR
                (EpicDueDate BETWEEN ? AND ?)
            )
            """
            df_anterior = pd.read_sql(query_anterior, conn, params=[dt_inicio_anterior, dt_fim_anterior, dt_inicio_anterior, dt_fim_anterior])

            if not df_anterior.empty:
                epicos_anterior = convert_numpy_types(df_anterior.iloc[0]['total_epicos'])
                if epicos_anterior > 0:
                    tendencia = round(((epicos_atual - epicos_anterior) / epicos_anterior) * 100, 1)
                else:
                    tendencia = None
        else:
            tendencia = None

        stats['tendencia_epicos'] = tendencia

        
        #  Adicionar informação do período para o frontend
        periodo_info = {
            'periodo_selecionado': periodo_filter,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'descricao': get_periodo_description(periodo_filter)
        }
        
        conn.close()
        
        return jsonify({
            'stats': stats,
            'equipes': equipes,
            'status_distribution': status_distribution,
            'periodo_info': periodo_info,
            'filtros_aplicados': {
                'equipe': equipe_filter,
                'produto': produto_filter,
                'status': status_filter,
                'periodo': periodo_filter
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})



# Função auxiliar para descrição do período

def get_periodo_description(periodo):
    """Retorna descrição do período selecionado - ATUALIZADA"""
    today = datetime.now()
    current_year = today.year
    
    descriptions = {
        'ano_atual': f"Ano de {current_year}",
        'q1': f"Q1 {current_year} (Janeiro a Março)",
        'q2': f"Q2 {current_year} (Abril a Junho)", 
        'q3': f"Q3 {current_year} (Julho a Setembro)",
        'q4': f"Q4 {current_year} (Outubro a Dezembro)",
        '6_meses': "Últimos 6 meses",
        '3_meses': "Últimos 3 meses",
        'mes_atual': today.strftime('%B de %Y'),
        'todos': "Todos os períodos",
        'personalizado': "Período personalizado"
    }
    return descriptions.get(periodo, "Período personalizado")

# Atualização para as funções de filtro de período - NOVA LÓGICA
def calculate_period_dates(periodo_filter):
    """Calcula datas de início e fim baseado no período selecionado"""
    today = datetime.now()
    current_year = today.year
    
    if periodo_filter == 'ano_atual':
        data_inicio = f"{current_year}-01-01"
        data_fim = f"{current_year}-12-31"
    elif periodo_filter == 'q1':
        data_inicio = f"{current_year}-01-01"
        data_fim = f"{current_year}-03-31"
    elif periodo_filter == 'q2':
        data_inicio = f"{current_year}-04-01"
        data_fim = f"{current_year}-06-30"
    elif periodo_filter == 'q3':
        data_inicio = f"{current_year}-07-01"
        data_fim = f"{current_year}-09-30"
    elif periodo_filter == 'q4':
        data_inicio = f"{current_year}-10-01"
        data_fim = f"{current_year}-12-31"
    elif periodo_filter == '6_meses':
        data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
        data_fim = today.strftime('%Y-%m-%d')
    elif periodo_filter == '3_meses':
        data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
        data_fim = today.strftime('%Y-%m-%d')
    elif periodo_filter == 'mes_atual':
        data_inicio = f"{current_year}-{today.month:02d}-01"
        data_fim = today.strftime('%Y-%m-%d')
    else:  # 'todos' ou 'personalizado'
        data_inicio = None
        data_fim = None
        
    return data_inicio, data_fim

@app.route('/api/alertas-detalhes')
def alertas_detalhes():
    """API para obter detalhes dos alertas"""
    try:
        tipo_alerta = request.args.get('tipo', '')
        conn = db_manager.get_connection()
        
        if tipo_alerta == 'atrasados':
            # Épicos atrasados
            query = """
            SELECT 
                EpicNumber,
                EpicSummary,
                EpicEquipe,
                EpicStatus,
                EpicDueDate,
                DATEDIFF(day, EpicDueDate, GETDATE()) as DiasAtraso,
                CAST(ISNULL(TasksPercentualMedia, 0) as decimal(5,2)) as PercentualConcluido
            FROM BI_Jira_Epico_Datas_Grafico
            WHERE EpicDueDate < GETDATE() 
            And TipoRegistroCalculo = 'Planejado Time'
            AND EpicStatus NOT IN ('Done', 'Closed')
            AND EpicInicioPlanejado IS NOT NULL
            ORDER BY EpicDueDate
            """
            
        elif tipo_alerta == 'proximo_prazo':
            # Épicos que vencem nos próximos 7 dias
            query = """
            SELECT 
                EpicNumber,
                EpicSummary,
                EpicEquipe,
                EpicStatus,
                EpicDueDate,
                DATEDIFF(day, GETDATE(), EpicDueDate) as DiasRestantes,
                CAST(ISNULL(TasksPercentualMedia, 0) as decimal(5,2)) as PercentualConcluido
            FROM BI_Jira_Epico_Datas_Grafico
            WHERE EpicDueDate BETWEEN GETDATE() AND DATEADD(day, 7, GETDATE())
            And TipoRegistroCalculo = 'Planejado Time'
            AND EpicStatus NOT IN ('Done', 'Closed')
            AND EpicInicioPlanejado IS NOT NULL
            ORDER BY EpicDueDate
            """
            
        elif tipo_alerta == 'baixo_progresso':
            # Épicos com baixo progresso (menos de 30% e iniciados há mais de 15 dias)
            query = """
            SELECT 
                EpicNumber,
                EpicSummary,
                EpicEquipe,
                EpicStatus,
                EpicInicioPlanejado,
                EpicDueDate,
                CAST(ISNULL(TasksPercentualMedia, 0) as decimal(5,2)) as PercentualConcluido,
                DATEDIFF(day, EpicInicioPlanejado, GETDATE()) as DiasDecorridos
            FROM BI_Jira_Epico_Datas_Grafico
            WHERE CAST(ISNULL(TasksPercentualMedia, 0) as decimal(5,2)) < 30
            And TipoRegistroCalculo = 'Planejado Time'
            AND EpicInicioPlanejado < DATEADD(day, -15, GETDATE())
            AND EpicStatus NOT IN ('Done', 'Closed')
            AND EpicInicioPlanejado IS NOT NULL
            ORDER BY TasksPercentualMedia, EpicInicioPlanejado
            """
            
        else:
            return jsonify({'error': 'Tipo de alerta não reconhecido'})
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Converter datas para string
        date_columns = [col for col in df.columns if 'Date' in col or 'Inicio' in col or 'Fim' in col]
        for col in date_columns:
            if col in df.columns and not df[col].empty:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d/%m/%Y')
        
        registros = convert_numpy_types(df.fillna('').to_dict('records'))
        
        return jsonify({
            'tipo': tipo_alerta,
            'registros': registros,
            'total': len(registros)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

# ===============================
# ROTAS DO GANTT
# ===============================

@app.route('/gantt')
def gantt():
    """Página do gráfico de Gantt"""
    return render_template('gantt.html')

@app.route('/api/gantt')
def gantt_redirect():
    return gantt_data()  

@app.route('/api/gantt-data')
def gantt_data():
    """API para dados do gráfico de Gantt AGRUPADO POR ÉPICO com Indicadores """
    try:
        log_message("=== INICIANDO GANTT AGRUPADO COM INDICADORES  ===")
        
        # Testar conexão primeiro
        log_message("Testando conexão com banco...")
        success, message = db_manager.test_connection()
        if not success:
            error_msg = f"Erro de conexão: {message}"
            log_message(f"ERRO: {error_msg}")
            return jsonify({'error': error_msg})
        
        log_message("Conexão OK - obtendo parâmetros...")
        
        conn = db_manager.get_connection()
        
        # Obter filtros da requisição
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        
        # verificar se são datas personalizadas ou período pré-definido
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio_custom = request.args.get('data_inicio', '').strip()
        data_fim_custom = request.args.get('data_fim', '').strip()
        
        today = datetime.now()
        current_year = today.year
        
        # Se há datas customizadas, usar elas. Senão, calcular pelo período
        if data_inicio_custom and data_fim_custom:
            data_inicio = data_inicio_custom
            data_fim = data_fim_custom
        else:
            data_inicio, data_fim = calculate_period_dates(periodo_filter)
            # Se ainda não tiver datas (período 'todos'), usar padrão
            if not data_inicio:
                data_inicio = f"{current_year}-01-01"
            if not data_fim:
                data_fim = f"{current_year}-12-31"
        
        log_message(f"Filtros: equipe='{equipe_filter}', status='{status_filter}', periodo='{periodo_filter}', inicio='{data_inicio}', fim='{data_fim}'")
        
        # Query ATUALIZADA para usar a estrutura real da tabela
        query = """
        SELECT 
            CAST(ISNULL(EpicNumber, 'Epic-0') AS VARCHAR(50)) as EpicNumber,
            CAST(ISNULL(EpicSummary, 'Sem resumo') AS VARCHAR(500)) as EpicSummary,
            CAST(ISNULL(EpicEquipe, 'Sem Equipe') AS VARCHAR(100)) as EpicEquipe,
            CAST(ISNULL(EpicStatus, 'Indefinido') AS VARCHAR(50)) as EpicStatus,
            CAST(ISNULL(EpicProduto, 'Sem Produto') AS VARCHAR(100)) as EpicProduto,
            EpicInicioPlanejado,
            EpicDueDate,
            TasksDataInicial,
            TasksDataFim,
            CAST(ISNULL(TasksPercentualMedia, 0) AS DECIMAL(7,2)) as TasksPercentualMedia,
            CAST(ISNULL(TipoRegistroCalculo, 'Indefinido') AS VARCHAR(100)) as TipoRegistroCalculo,
            CAST(ISNULL(IndicadorAndamentoEpico, 'Verde') AS VARCHAR(100)) as IndicadorAndamentoEpico
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicInicioPlanejado IS NOT NULL 
        AND EpicDueDate IS NOT NULL
        AND TipoRegistroCalculo IS NOT NULL
        AND (
            -- Épicos que começam OU terminam no período especificado
            (EpicDueDate >= ? AND EpicDueDate <= ?) OR
            (EpicInicioPlanejado >= ? AND EpicInicioPlanejado <= ?) OR
            -- Épicos que começam antes e terminam depois (atravessam o período)
            (EpicInicioPlanejado < ? AND EpicDueDate > ?)
        )
        """
        
        params = [data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim]
        
        if equipe_filter and equipe_filter != '':
            query += " AND ISNULL(EpicEquipe, '') = ?"
            params.append(equipe_filter)
            
        if status_filter and status_filter != '':
            query += " AND ISNULL(EpicStatus, '') = ?"
            params.append(status_filter)
            
        query += " ORDER BY EpicEquipe, EpicNumber, TipoRegistroCalculo"
        
        log_message(f"Executando query com {len(params)} parâmetros...")
        
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        log_message(f"DataFrame retornou {len(df)} linhas")
        
        if df.empty:
            log_message("DataFrame vazio - retornando mensagem")
            return jsonify({
                'message': 'Nenhum dado encontrado para os filtros selecionados',
                'equipes': [],
                'status': [],
                'total_epicos': 0
            })
        
        # NOVA LÓGICA: Agrupar por épico e criar subgrupos
        gantt_data = []
        epicos_agrupados = df.groupby(['EpicNumber', 'EpicSummary', 'EpicEquipe', 'EpicStatus'])
        
        log_message("Processando dados agrupados por épico...")
        
        for (epic_number, epic_summary, epic_equipe, epic_status), grupo in epicos_agrupados:
            try:
                log_message(f"Processando épico {epic_number}")
                
                epic_number_str = str(epic_number) if epic_number is not None else "Epic-0"
                # Remover caracteres especiais que podem quebrar JSON
                epic_summary_str = str(epic_summary) if epic_summary is not None else "Sem resumo"
                epic_summary_str = epic_summary_str.replace('"', "'").replace('\n', ' ').replace('\r', ' ')
                epic_equipe_str = str(epic_equipe) if epic_equipe is not None else "Sem Equipe"
                
                # Truncar resumo se muito longo
                if len(epic_summary_str) > 60:
                    epic_summary_str = epic_summary_str[:60] + "..."
                
                # Base do nome da task (épico)
                task_base_name = f"{epic_number_str} - {epic_summary_str}"
                
                # Processar cada tipo de registro (Planejado P.O., Planejado Time, Realizado Time)
                for index, row in grupo.iterrows():
                    tipo_registro = row['TipoRegistroCalculo']
                    indicador_andamento = row['IndicadorAndamentoEpico']
                    
                    # Definir configurações baseadas no tipo de registro
                    if tipo_registro == 'Planejado P.O.':
                        task_prefix = "📋 PO"
                        base_color = '#6c757d'  # Cinza base
                        opacity = 0.7
                        width = 18
                        tipo_display = "PLANEJADO P.O."
                    elif tipo_registro == 'Planejado Time':
                        task_prefix = "⏰ Time"
                        base_color = '#17a2b8'  # Azul base
                        opacity = 0.85
                        width = 22
                        tipo_display = "PLANEJADO TIME"
                    elif tipo_registro == 'Realizado Time':
                        task_prefix = "✅ Real"
                        # Para o realizado, usar a cor baseada no indicador
                        if indicador_andamento == 'Verde':
                            base_color = '#28a745'  # Verde
                        elif indicador_andamento == 'Amarelo':
                            base_color = '#ffc107'  # Amarelo
                        elif indicador_andamento == 'Vermelho':
                            base_color = '#dc3545'  # Vermelho
                        else:
                            base_color = '#6c757d'  # Cinza padrão
                        
                        opacity = 1.0
                        width = 26
                        tipo_display = "REALIZADO TIME"
                    else:
                        log_message(f"  Tipo de registro não reconhecido: {tipo_registro}")
                        continue  # Pular tipos não reconhecidos
                    
                    # Nome completo da task 
                    task_name = f"  {task_prefix}: {task_base_name}"
                    
                    # Datas de início e fim
                    task_start = row['TasksDataInicial']
                    task_finish = row['TasksDataFim']
                    
                    if pd.isna(task_start) or pd.isna(task_finish):
                        log_message(f"  Pulando {tipo_registro} - datas inválidas")
                        continue
                    
                    # Descrição do indicador para hover - SEM EMOJIS
                    indicador_descricao_map = {
                        'Verde': 'Dentro do Prazo/Concluido',
                        'Amarelo': 'Proximo do Prazo (<=5 dias)',
                        'Vermelho': 'Atrasado/Critico'
                    }
                    indicador_descricao = indicador_descricao_map.get(indicador_andamento, 'Indefinido')
                    
                    gantt_data.append({
                        'Task': task_name,
                        'Start': task_start.strftime('%Y-%m-%d') if pd.notna(task_start) else None,
                        'Finish': task_finish.strftime('%Y-%m-%d') if pd.notna(task_finish) else None,
                        'Resource': epic_equipe_str,
                        'Complete': float(row['TasksPercentualMedia']) if pd.notna(row['TasksPercentualMedia']) else 0.0,
                        'Status': str(epic_status),
                        'TipoRegistro': tipo_registro,
                        'TipoDisplay': tipo_display,
                        'EpicNumber': epic_number_str,
                        'IndicadorAndamento': indicador_andamento,
                        'IndicadorDescricao': indicador_descricao,
                        'Color': base_color,
                        'Opacity': opacity,
                        'Width': width
                    })
                
                log_message(f"  Épico {epic_number_str} processado com {len(grupo)} registros")
                
            except Exception as e:
                log_message(f"ERRO no épico {epic_number}: {e}")
                continue
        
        log_message(f"Total processado: {len(gantt_data)} itens")
        
        if not gantt_data:
            return jsonify({
                'message': 'Nenhum épico com datas válidas encontrado',
                'equipes': [],
                'status': [],
                'total_epicos': 0
            })
        
        # Criar gráfico Plotly com AGRUPAMENTO e INDICADORES
        log_message("Criando gráfico Plotly agrupado com indicadores...")
        
        fig = go.Figure()
        
        # Controle de legendas por tipo de registro
        legendas_mostradas = {
            'Planejado P.O.': False,
            'Planejado Time': False,
            'Realizado Time': False
        }
        
        # Criar traces para cada item
        for i, item in enumerate(gantt_data):
            
            tipo_registro = item['TipoRegistro']
            
            # Mostrar legenda apenas uma vez por tipo
            show_legend = not legendas_mostradas[tipo_registro]
            legendas_mostradas[tipo_registro] = True
            
            # Nome para a legenda - SEM EMOJIS
            legend_names = {
                'Planejado P.O.': 'Planejado P.O.',
                'Planejado Time': 'Planejado Time',
                'Realizado Time': 'Realizado Time'
            }
            legend_name = legend_names.get(tipo_registro, tipo_registro)
            
            # Remover caracteres especiais do hovertemplate
            hover_text = f"""<b>{item["TipoDisplay"]}</b><br>
<b>{item["Task"]}</b><br>
Equipe: {item["Resource"]}<br>
Inicio: {item["Start"]}<br>
Fim: {item["Finish"]}<br>
Progresso: {item["Complete"]}%<br>
Status: {item["Status"]}<br>
Indicador: {item["IndicadorDescricao"]}<br>
<extra></extra>"""
            
            fig.add_trace(go.Scatter(
                x=[item['Start'], item['Finish']],
                y=[item['Task'], item['Task']],
                mode='lines',
                line=dict(
                    color=item['Color'],
                    width=item['Width']
                ),
                opacity=item['Opacity'],
                name=legend_name,
                showlegend=show_legend,
                legendgroup=tipo_registro.lower().replace(' ', '_').replace('.', ''),
                hovertemplate=hover_text,
                text=[item['Task'], item['Task']],
                hoverinfo='text'
            ))
        
        log_message(f"Total de traces adicionadas: {len(fig.data)}")
        
        # Calcular range de datas para zoom inicial correto
        all_dates = []
        for item in gantt_data:
            if item['Start']:
                all_dates.append(datetime.strptime(item['Start'], '%Y-%m-%d'))
            if item['Finish']:
                all_dates.append(datetime.strptime(item['Finish'], '%Y-%m-%d'))
        
        # Definir range de visualização
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            # Margem menor para melhor visualização
            from datetime import timedelta
            margin = timedelta(days=15)
            range_start = min_date - margin
            range_end = max_date + margin
            log_message(f"Range calculado: {range_start.strftime('%Y-%m-%d')} até {range_end.strftime('%Y-%m-%d')}")
        else:
            range_start = datetime.strptime(data_inicio, '%Y-%m-%d')
            range_end = datetime.strptime(data_fim, '%Y-%m-%d')
            log_message(f"Range padrão: {range_start.strftime('%Y-%m-%d')} até {range_end.strftime('%Y-%m-%d')}")
        
        # Adicionar linha vertical "HOJE"
        hoje_str = datetime.now().strftime('%Y-%m-%d')
        
        fig.add_shape(
            type="line",
            x0=hoje_str,
            x1=hoje_str,
            y0=0,
            y1=1,
            yref="paper",
            line=dict(
                color="red",
                width=3,
                dash="dash"
            )
        )
        
        # Adicionar anotação "HOJE"
        fig.add_annotation(
            x=hoje_str,
            y=1.05,
            yref="paper",
            text="<b>HOJE</b>",
            showarrow=False,
            font=dict(color="red", size=12, family="Arial Black"),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="red",
            borderwidth=2
        )
        
        # Configurar layout - AGRUPADO E RESPONSIVO
        fig.update_layout(
            title={
                'text': 'Roadmap de Epicos - Grafico de Gantt Agrupado<br><sub>Planejado PO | Planejado Time | Realizado (Indicadores por Cor)</sub>',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16}
            },
            
            # Altura baseada no número de itens (considerando agrupamento)
            height=max(800, len(gantt_data) * 30 + 200),
            
            # EIXO X PRINCIPAL (inferior)
            xaxis=dict(
                type='date',
                tickformat='%d/%m/%Y',
                dtick='M1',
                tickmode='linear',
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                tickangle=45,
                tickfont=dict(size=11),
                side='bottom',
                showline=True,
                linewidth=2,
                linecolor='black',
                title=dict(text='Data', font=dict(size=14)),
                autorange=False,
                range=[range_start, range_end]
            ),
            
            # EIXO X SUPERIOR
            xaxis2=dict(
                type='date',
                tickformat='%b/%Y',
                dtick='M1',
                tickmode='linear',
                showgrid=False,
                tickangle=0,
                tickfont=dict(size=12, color='blue'),
                side='top',
                showline=True,
                linewidth=2,
                linecolor='blue',
                overlaying='x',
                matches='x',
                title=dict(
                    text='Timeline Principal',
                    font=dict(size=14, color='blue')
                ),
                autorange=False,
                range=[range_start, range_end]
            ),
            
            # EIXO Y - Agrupado
            yaxis=dict(
                autorange='reversed',
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                tickfont=dict(size=9),  # Fonte menor para comportar mais itens
                side='left',
                showline=True,
                linewidth=2,
                linecolor='black',
                title=dict(text='Epicos por Tipo', font=dict(size=14))
            ),
            
            # MARGENS OTIMIZADAS para agrupamento
            margin=dict(l=480, r=50, t=180, b=120),
            
            # CORES E FONTES
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family="Arial, sans-serif", size=11),
            
            # LEGENDA HORIZONTAL
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(255,255,255,0.95)",
                bordercolor="gray",
                borderwidth=2,
                font=dict(size=12)
            ),
            
            showlegend=True,
            hovermode='closest',
            autosize=True
        )
        
        log_message("Layout configurado! Convertendo para JSON...")
        
        # Usar ensure_ascii=False para manter caracteres especiais, mas remover emojis problemáticos
        graphJSON = json.dumps(fig, cls=PlotlyJSONEncoder, ensure_ascii=False)
        
        # Obter listas para filtros (únicas)
        equipes_list = sorted(df['EpicEquipe'].dropna().unique().tolist())
        status_list = sorted(df['EpicStatus'].dropna().unique().tolist())
        
        # Contar épicos únicos
        total_epicos_unicos = df['EpicNumber'].nunique()
        
        log_message(f"SUCESSO! Retornando {total_epicos_unicos} épicos únicos com {len(gantt_data)} registros")
        log_message("=== FIM GANTT-DATA AGRUPADO COM INDICADORES ===")
        
        return jsonify({
            'gantt': graphJSON,
            'equipes': equipes_list,
            'status': status_list,
            'total_epicos': total_epicos_unicos
        })
        
    except Exception as e:
        import traceback
        error_msg = f"Erro no gantt-data: {str(e)}"
        traceback_msg = traceback.format_exc()
        log_message(f"ERRO CRÍTICO: {error_msg}")
        log_message(f"Traceback: {traceback_msg}")
        return jsonify({'error': error_msg})


 
@app.route('/relatorio-epicos')
def relatorio_epicos():
    """Página do relatório de épicos"""
    return render_template('relatorio_epicos.html')

@app.route('/api/epicos-data')
def epicos_data():
    """API para dados dos épicos"""
    try:
        conn = db_manager.get_connection()
        
        query = """
        SELECT * FROM BI_Jira_Epico_Datas_Grafico
        ORDER BY EpicEquipe, EpicNumber
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Converter datas para string para JSON
        date_columns = ['EpicInicioPlanejado', 'EpicDueDate', 'TasksDataInicial', 'TasksDataFim']
        for col in date_columns:
            if col in df.columns:
                df[col] = df[col].dt.strftime('%d/%m/%Y %H:%M') if df[col].dtype == 'datetime64[ns]' else df[col]
        
        return jsonify(df.fillna('').to_dict('records'))
        
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/export/epicos')
def export_epicos():
    """Exportar épicos para CSV com filtros aplicados - VERSÃO ATUALIZADA"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        search_filter = request.args.get('search', '').strip()
        data_inicio = request.args.get('data_inicio', '').strip()
        data_fim = request.args.get('data_fim', '').strip()
        
        # Log dos filtros recebidos
        log_message(f"Export épicos - Filtros: equipe={equipe_filter}, status={status_filter}, produto={produto_filter}, search={search_filter}, data_inicio={data_inicio}, data_fim={data_fim}")
        
        # Query base
        query = "SELECT * FROM BI_Jira_Epico_Datas_Grafico WHERE TipoRegistroCalculo = 'Planejado Time'"
        params = []
        
        # Aplicar filtros de equipe, status e produto
        if equipe_filter:
            query += " AND ISNULL(EpicEquipe, '') = ?"
            params.append(equipe_filter)
            
        if status_filter:
            query += " AND ISNULL(EpicStatus, '') = ?"
            params.append(status_filter)
            
        if produto_filter:
            query += " AND ISNULL(EpicProduto, '') = ?"
            params.append(produto_filter)
        
        # Aplicar filtro de data (mesmo filtro usado na tela)
        if data_inicio and data_fim:
            query += """ AND (
                (EpicDueDate >= ? AND EpicDueDate <= ?) OR
                (EpicInicioPlanejado >= ? AND EpicInicioPlanejado <= ?) OR
                (EpicInicioPlanejado < ? AND EpicDueDate > ?)
            )"""
            params.extend([data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim])
        elif data_inicio:
            query += " AND EpicInicioPlanejado >= ?"
            params.append(data_inicio)
        elif data_fim:
            query += " AND EpicDueDate <= ?"
            params.append(data_fim)
        
        query += " ORDER BY EpicEquipe, EpicNumber"
        
        log_message(f"Query de export: {query}")
        log_message(f"Parâmetros: {params}")
        
        # Executar query
        df = pd.read_sql(query, conn, params=params)
        log_message(f"Registros retornados antes do filtro de busca: {len(df)}")
        
        conn.close()
        
        # Aplicar filtro de busca (texto) no DataFrame - igual ao frontend
        if search_filter:
            search_lower = search_filter.lower()
            mask = (
                df['EpicNumber'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False) |
                df['EpicSummary'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False)
            )
            df = df[mask]
            log_message(f"Registros após filtro de busca '{search_filter}': {len(df)}")
        
        # Verificar se há dados para exportar
        if df.empty:
            log_message("Nenhum dado encontrado para exportar com os filtros aplicados")
            return jsonify({
                'error': 'Nenhum dado encontrado para exportar com os filtros aplicados'
            }), 404
        
        # Formatar datas para melhor visualização no CSV
        date_columns = ['EpicInicioPlanejado', 'EpicDueDate', 'TasksDataInicial', 'TasksDataFim']
        for col in date_columns:
            if col in df.columns:
                # Converter para datetime se não estiver e depois para string
                try:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
                except:
                    pass
        
        # Preencher valores nulos
        df = df.fillna('')
        
        # Criar arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False)
        
        # Salvar com encoding UTF-8 com BOM para Excel
        df.to_csv(temp_file.name, index=False, encoding='utf-8-sig', sep=';')
        
        # Construir nome do arquivo com informações sobre os filtros
        filename_parts = ['relatorio_epicos']
        
        if equipe_filter:
            equipe_clean = equipe_filter.replace(' ', '_').replace('/', '_')
            filename_parts.append(f"equipe_{equipe_clean}")
            
        if status_filter:
            status_clean = status_filter.replace(' ', '_').replace('/', '_')
            filename_parts.append(f"status_{status_clean}")
            
        if produto_filter:
            produto_clean = produto_filter.replace(' ', '_').replace('/', '_')
            filename_parts.append(f"produto_{produto_clean}")
            
        if search_filter:
            search_clean = search_filter.replace(' ', '_').replace('/', '_')[:10]  # Limitar tamanho
            filename_parts.append(f"busca_{search_clean}")
            
        if data_inicio or data_fim:
            if data_inicio and data_fim:
                filename_parts.append(f"{data_inicio}_a_{data_fim}")
            elif data_inicio:
                filename_parts.append(f"desde_{data_inicio}")
            elif data_fim:
                filename_parts.append(f"ate_{data_fim}")
        
        # Adicionar timestamp e total de registros
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_parts.append(f"{len(df)}registros")
        filename_parts.append(timestamp)
        
        filename = '_'.join(filename_parts) + '.csv'
        
        # Limitar tamanho do nome do arquivo
        if len(filename) > 200:
            filename = f"relatorio_epicos_{len(df)}registros_{timestamp}.csv"
        
        log_message(f"Exportando {len(df)} registros para arquivo: {filename}")
        
        return send_file(temp_file.name, 
                        as_attachment=True, 
                        download_name=filename,
                        mimetype='text/csv')
        
    except Exception as e:
        error_msg = f"Erro na exportação de épicos: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg}), 500


# SubTasks 

@app.route('/relatorio-subtasks')
def relatorio_subtasks():
    """Página do relatório de subtasks"""
    return render_template('relatorio_subtasks.html')

@app.route('/api/subtasks-data')
def subtasks_data():
    """API para dados das subtasks seguindo o padrão dos épicos"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros (igual ao padrão dos épicos)
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        tipo_filter = request.args.get('tipo', '').strip()
        subTipo_filter = request.args.get('subTipo', '').strip()
        search_filter = request.args.get('search', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio_custom = request.args.get('data_inicio', '').strip()
        data_fim_custom = request.args.get('data_fim', '').strip()
        
        log_message(f"SubTasks API - Filtros recebidos: equipe='{equipe_filter}', status='{status_filter}', tipo='{tipo_filter}', subTipo='{subTipo_filter}', search='{search_filter}', periodo='{periodo_filter}', data_inicio='{data_inicio_custom}', data_fim='{data_fim_custom}'")
        
        # Calcular datas baseadas no período (mesmo que o export)
        today = datetime.now()
        current_year = today.year
        
        # Determinar datas baseadas no período
        if data_inicio_custom and data_fim_custom:
            data_inicio = data_inicio_custom
            data_fim = data_fim_custom
        elif periodo_filter == 'ano_atual':
            data_inicio = f"{current_year}-01-01"
            data_fim = f"{current_year}-12-31"
        elif periodo_filter == 'q1':
            data_inicio = f"{current_year}-01-01"
            data_fim = f"{current_year}-03-31"
        elif periodo_filter == 'q2':
            data_inicio = f"{current_year}-04-01"
            data_fim = f"{current_year}-06-30"
        elif periodo_filter == 'q3':
            data_inicio = f"{current_year}-07-01"
            data_fim = f"{current_year}-09-30"
        elif periodo_filter == 'q4':
            data_inicio = f"{current_year}-10-01"
            data_fim = f"{current_year}-12-31"
        elif periodo_filter == '6_meses':
            data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == '3_meses':
            data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == 'mes_atual':
            data_inicio = f"{current_year}-{today.month:02d}-01"
            data_fim = today.strftime('%Y-%m-%d')
        else:
            # Para 'personalizado' sem datas ou outros valores, não aplicar filtro de data
            data_inicio = None
            data_fim = None
        
        # Query base com filtros de período aplicados no backend (para performance)
        query = "SELECT * FROM BI_Jira_SubTasks_Datas_Grafico WHERE 1=1"
        params = []
        
        # Aplicar filtro de data se tiver (para reduzir volume de dados)
        if data_inicio and data_fim:
            query += """ AND (
                (TaskFimPlanejado >= ? AND TaskFimPlanejado <= ?) OR
                (TaskInicioPlanejado >= ? AND TaskInicioPlanejado <= ?) OR
                (TaskInicioPlanejado < ? AND TaskFimPlanejado > ?)
            )"""
            params.extend([data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim])
            log_message(f"SubTasks API - Aplicando filtro de período: {data_inicio} até {data_fim}")
        elif data_inicio:
            query += " AND TaskInicioPlanejado >= ?"
            params.append(data_inicio)
            log_message(f"SubTasks API - Aplicando filtro de início: {data_inicio}")
        elif data_fim:
            query += " AND TaskFimPlanejado <= ?"
            params.append(data_fim)
            log_message(f"SubTasks API - Aplicando filtro de fim: {data_fim}")
        
        query += " ORDER BY TaskEquipe, TaskProjectKey"
        
        log_message(f"SubTasks Query: {query}")
        log_message(f"SubTasks Params: {params}")
        
        # Executar query com filtros de período aplicados
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        log_message(f"SubTasks - Registros retornados do banco após filtro de período: {len(df)}")
        
        # Converter datas para string para JSON
        date_columns = [col for col in df.columns if 'date' in col.lower() or 'inicio' in col.lower() or 'fim' in col.lower() or 'created' in col.lower() or 'updated' in col.lower()]
        for col in date_columns:
            if col in df.columns and not df[col].empty:
                try:
                    # Tentar converter para datetime e depois para string
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
                except:
                    # Se falhar, manter como está
                    pass
        
        # Converter tipos numpy e retornar dados filtrados por período
        result = convert_numpy_types(df.fillna('').to_dict('records'))
        log_message(f"SubTasks - Retornando {len(result)} registros (com filtros de período aplicados)")
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Erro na API de subtasks: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg})

@app.route('/api/exportar-subtasks')
def exportar_subtasks():
    try:
        conn = db_manager.get_connection()
        query = """
        SELECT *
        FROM BI_Jira_SubTasks_Datas_Grafico
        WHERE TasksDataInicial IS NOT NULL
        ORDER BY EpicNumber, TasksDataInicial
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # Salva em arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        df.to_excel(temp_file.name, index=False)

        return send_file(temp_file.name, as_attachment=True, download_name="subtasks_exportadas.xlsx")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Função auxiliar para limpeza de arquivos temporários (opcional)
def cleanup_temp_files():
    """Limpar arquivos temporários antigos"""
    try:
        import glob
        import time
        temp_pattern = os.path.join(tempfile.gettempdir(), "tmp*.csv")
        for temp_file in glob.glob(temp_pattern):
            try:
                # Deletar arquivos temporários com mais de 1 hora
                if time.time() - os.path.getctime(temp_file) > 3600:
                    os.unlink(temp_file)
            except:
                pass
    except:
        pass 
    """Exportar épicos para CSV com filtros aplicados"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        search_filter = request.args.get('search', '').strip()
        data_inicio = request.args.get('data_inicio', '')
        data_fim = request.args.get('data_fim', '')
        
        # Query base
        query = "SELECT * FROM BI_Jira_Epico_Datas_Grafico WHERE 1=1"
        params = []
        
        # Aplicar filtros de equipe, status e produto
        if equipe_filter:
            query += " AND ISNULL(EpicEquipe, '') = ?"
            params.append(equipe_filter)
            
        if status_filter:
            query += " AND ISNULL(EpicStatus, '') = ?"
            params.append(status_filter)
            
        if produto_filter:
            query += " AND ISNULL(EpicProduto, '') = ?"
            params.append(produto_filter)
        
        # Aplicar filtro de data (mesmo filtro do Gantt)
        if data_inicio and data_fim:
            query += """ AND (
                (EpicDueDate >= ? AND EpicDueDate <= ?) OR
                (EpicInicioPlanejado >= ? AND EpicInicioPlanejado <= ?) OR
                (EpicInicioPlanejado < ? AND EpicDueDate > ?)
            )"""
            params.extend([data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim])
        elif data_inicio:
            query += " AND EpicInicioPlanejado >= ?"
            params.append(data_inicio)
        elif data_fim:
            query += " AND EpicDueDate <= ?"
            params.append(data_fim)
        
        query += " ORDER BY EpicEquipe, EpicNumber"
        
        # Executar query
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        # Aplicar filtro de busca (texto) no DataFrame
        if search_filter:
            search_lower = search_filter.lower()
            mask = (
                df['EpicNumber'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False) |
                df['EpicSummary'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False)
            )
            df = df[mask]
        
        # Criar arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False)
        df.to_csv(temp_file.name, index=False, encoding='utf-8-sig')
        
        # Nome do arquivo com informações sobre os filtros
        filename_parts = ['relatorio_epicos']
        if equipe_filter:
            filename_parts.append(f"equipe_{equipe_filter.replace(' ', '_')}")
        if status_filter:
            filename_parts.append(f"status_{status_filter.replace(' ', '_')}")
        if data_inicio or data_fim:
            if data_inicio and data_fim:
                filename_parts.append(f"{data_inicio}_a_{data_fim}")
            elif data_inicio:
                filename_parts.append(f"desde_{data_inicio}")
            elif data_fim:
                filename_parts.append(f"ate_{data_fim}")
        
        filename_parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
        filename = '_'.join(filename_parts) + '.csv'
        
        return send_file(temp_file.name, 
                        as_attachment=True, 
                        download_name=filename,
                        mimetype='text/csv')
        
    except Exception as e:
        return jsonify({'error': str(e)})
    
@app.route('/export/subtasks')  
def export_subtasks():
    """Exportar subtasks para CSV """
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros (usando o mesmo padrão dos épicos)
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        tipo_filter = request.args.get('tipo', '').strip()
        subTipo_filter = request.args.get('subTipo', '').strip()
        search_filter = request.args.get('search', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio_custom = request.args.get('data_inicio', '').strip()
        data_fim_custom = request.args.get('data_fim', '').strip()
        
        # Log dos filtros recebidos
        log_message(f"Export SubTasks - Filtros: equipe={equipe_filter}, status={status_filter}, tipo={tipo_filter}, subTipo={subTipo_filter}, search={search_filter}, periodo={periodo_filter}, data_inicio={data_inicio_custom}, data_fim={data_fim_custom}")
        
        # Query base - iniciar sem filtros
        query = "SELECT * FROM BI_Jira_SubTasks_Datas_Grafico WHERE 1=1"
        params = []
        
        # Aplicar filtros básicos apenas se fornecidos
        if equipe_filter:
            query += " AND ISNULL(TaskEquipe, '') = ?"
            params.append(equipe_filter)
            
        if status_filter:
            query += " AND ISNULL(TaskStatus, '') = ?"
            params.append(status_filter)
            
        if tipo_filter:
            query += " AND ISNULL(TaskType, '') = ?"
            params.append(tipo_filter)
            
        
        # Aplicar filtros de data baseado no período (igual aos épicos)
        today = datetime.now()
        current_year = today.year
        
        # Determinar datas baseadas no período
        if data_inicio_custom and data_fim_custom:
            data_inicio = data_inicio_custom
            data_fim = data_fim_custom
        elif periodo_filter == 'ano_atual':
            data_inicio = f"{current_year}-01-01"
            data_fim = f"{current_year}-12-31"
        elif periodo_filter == 'q1':
            data_inicio = f"{current_year}-01-01"
            data_fim = f"{current_year}-03-31"
        elif periodo_filter == 'q2':
            data_inicio = f"{current_year}-04-01"
            data_fim = f"{current_year}-06-30"
        elif periodo_filter == 'q3':
            data_inicio = f"{current_year}-07-01"
            data_fim = f"{current_year}-09-30"
        elif periodo_filter == 'q4':
            data_inicio = f"{current_year}-10-01"
            data_fim = f"{current_year}-12-31"
        elif periodo_filter == '6_meses':
            data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == '3_meses':
            data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == 'mes_atual':
            data_inicio = f"{current_year}-{today.month:02d}-01"
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == 'personalizado':
            # Para personalizado sem datas específicas, não aplicar filtro de data
            data_inicio = None
            data_fim = None
        else:
            data_inicio = None
            data_fim = None
        
        # Aplicar filtro de data se tiver
        if data_inicio and data_fim:
            query += """ AND (
                (TaskFimPlanejado >= ? AND TaskFimPlanejado <= ?) OR
                (TaskInicioPlanejado >= ? AND TaskInicioPlanejado <= ?) OR
                (TaskInicioPlanejado < ? AND TaskFimPlanejado > ?)
            )"""
            params.extend([data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim])
        elif data_inicio:
            query += " AND TaskInicioPlanejado >= ?"
            params.append(data_inicio)
        elif data_fim:
            query += " AND TaskFimPlanejado <= ?"
            params.append(data_fim)
        
        query += " ORDER BY TaskEquipe, TaskNumberId"
        
        log_message(f"Export SubTasks Query: {query}")
        log_message(f"Export SubTasks Params: {params}")
        
        # Executar query
        df = pd.read_sql(query, conn, params=params)
        log_message(f"SubTasks Export - Registros retornados antes do filtro de busca: {len(df)}")
        
        conn.close()
        
        # Aplicar filtro de busca (texto) no DataFrame - igual ao frontend
        if search_filter:
            search_lower = search_filter.lower()
            mask = (
                df['TaskNumberId'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False) |
                df['TaskSummary'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False)
            )
            df = df[mask]
            log_message(f"SubTasks Export - Registros após filtro de busca '{search_filter}': {len(df)}")
        
        # Verificar se há dados para exportar
        if df.empty:
            log_message("Nenhum dado encontrado para exportar SubTasks com os filtros aplicados")
            return jsonify({
                'error': 'Nenhum dado encontrado para exportar com os filtros aplicados'
            }), 404
        
        # Formatar datas para melhor visualização no CSV
        date_columns = [col for col in df.columns if 'date' in col.lower() or 'inicio' in col.lower() or 'fim' in col.lower() or 'created' in col.lower() or 'updated' in col.lower()]
        for col in date_columns:
            if col in df.columns:
                try:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
                except:
                    pass
        
        # Preencher valores nulos
        df = df.fillna('')
        
        # Criar arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False)
        
        # Salvar com encoding UTF-8 com BOM para Excel
        df.to_csv(temp_file.name, index=False, encoding='utf-8-sig', sep=';')
        
        # Construir nome do arquivo com informações sobre os filtros
        filename_parts = ['relatorio_subtasks']
        
        if equipe_filter:
            equipe_clean = equipe_filter.replace(' ', '_').replace('/', '_')
            filename_parts.append(f"equipe_{equipe_clean}")
            
        if status_filter:
            status_clean = status_filter.replace(' ', '_').replace('/', '_')
            filename_parts.append(f"status_{status_clean}")
            
        if tipo_filter:
            tipo_clean = tipo_filter.replace(' ', '_').replace('/', '_')
            filename_parts.append(f"tipo_{tipo_clean}")
            
        if subTipo_filter:
            subTipo_clean = subTipo_filter.replace(' ', '_').replace('/', '_')
            filename_parts.append(f"subTipo_{subTipo_clean}")
            
        if search_filter:
            search_clean = search_filter.replace(' ', '_').replace('/', '_')[:10]  # Limitar tamanho
            filename_parts.append(f"busca_{search_clean}")
            
        if periodo_filter and periodo_filter != 'ano_atual':
            filename_parts.append(f"periodo_{periodo_filter}")
            
        if data_inicio or data_fim:
            if data_inicio and data_fim:
                filename_parts.append(f"{data_inicio}_a_{data_fim}")
            elif data_inicio:
                filename_parts.append(f"desde_{data_inicio}")
            elif data_fim:
                filename_parts.append(f"ate_{data_fim}")
        
        # Adicionar timestamp e total de registros
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_parts.append(f"{len(df)}registros")
        filename_parts.append(timestamp)
        
        filename = '_'.join(filename_parts) + '.csv'
        
        # Limitar tamanho do nome do arquivo
        if len(filename) > 200:
            filename = f"relatorio_subtasks_{len(df)}registros_{timestamp}.csv"
        
        log_message(f"Exportando SubTasks - {len(df)} registros para arquivo: {filename}")
        
        return send_file(temp_file.name, 
                        as_attachment=True, 
                        download_name=filename,
                        mimetype='text/csv')
        
    except Exception as e:
        error_msg = f"Erro na exportação de subtasks: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg}), 500

# MANS

@app.route('/relatorio-mans')
def relatorio_mans_page():
    """Página do relatório de MANs"""
    return render_template('relatorio_mans.html')

@app.route('/api/mans-data')
def mans_data():
    try:
        conn = db_manager.get_connection()
        query = """
        SELECT * FROM BI_Jira_US 
        WHERE Project = 'MAN' 
        """
        df = pd.read_sql(query, conn)
        conn.close()

        def limpar_dados(obj):
            """Converte valores problemáticos como NaT e numpy types"""
            if isinstance(obj, dict):
                return {k: limpar_dados(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [limpar_dados(v) for v in obj]
            elif pd.isna(obj):
                return None
            elif hasattr(obj, 'item'):
                return obj.item()
            elif hasattr(obj, 'isoformat'):  # Timestamp
                return obj.isoformat()
            else:
                return obj

        return jsonify(limpar_dados(df.to_dict(orient='records')))
    
    except Exception as e:
        return jsonify({'error': str(e)})
    
@app.route('/api/mans-data')
def mans_data_api():
    """API principal para dados de MANs """
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        busca_filter = request.args.get('busca', '').strip()
        search_filter = request.args.get('search', '').strip()
        ano_filter = request.args.get('ano', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio_custom = request.args.get('data_inicio', '').strip()
        data_fim_custom = request.args.get('data_fim', '').strip()
        
        # Usar busca ou search (compatibilidade)
        search_text = busca_filter or search_filter
        
        log_message(f"MANs Data API - Filtros: equipe={equipe_filter}, status={status_filter}, produto={produto_filter}, busca={search_text}, periodo={periodo_filter}")
        
        # Calcular datas baseadas no período
        today = datetime.now()
        current_year = today.year
        
        if data_inicio_custom and data_fim_custom:
            data_inicio = data_inicio_custom
            data_fim = data_fim_custom
        elif periodo_filter == 'ano_atual':
            data_inicio = f"{current_year}-01-01"
            data_fim = f"{current_year}-12-31"
        elif periodo_filter == 'q1':
            data_inicio = f"{current_year}-01-01"
            data_fim = f"{current_year}-03-31"
        elif periodo_filter == 'q2':
            data_inicio = f"{current_year}-04-01"
            data_fim = f"{current_year}-06-30"
        elif periodo_filter == 'q3':
            data_inicio = f"{current_year}-07-01"
            data_fim = f"{current_year}-09-30"
        elif periodo_filter == 'q4':
            data_inicio = f"{current_year}-10-01"
            data_fim = f"{current_year}-12-31"
        elif periodo_filter == '6_meses':
            data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == '3_meses':
            data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
            data_fim = today.strftime('%Y-%m-%d')
        elif periodo_filter == 'mes_atual':
            data_inicio = f"{current_year}-{today.month:02d}-01"
            data_fim = today.strftime('%Y-%m-%d')
        else:
            data_inicio = None
            data_fim = None
        
        # Query base para dados de MANs
        query = """
        SELECT 
            ID,
            ISSUE_ID,
            Number,
            Project,
            ProjectKey,
            IssueType,
            Summary,
            Produto,
            ParentEpicID,
            ParentEpicNumber,
            Equipe,
            Assignee,
            Status,
            Created,
            Updated,
            ResolutionDate,
            OrigemAbertura,
            ServicePackLiberacao,
            PatchLiberacao,
            QtdeVinculos
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        """
        
        params = []
        
        # Aplicar filtro de data se tiver (para reduzir volume de dados)
        if data_inicio and data_fim:
            query += " AND Created BETWEEN ? AND ?"
            params.extend([data_inicio, data_fim])
            log_message(f"MANs API - Aplicando filtro de período: {data_inicio} até {data_fim}")
        elif data_inicio:
            query += " AND Created >= ?"
            params.append(data_inicio)
        elif data_fim:
            query += " AND Created <= ?"
            params.append(data_fim)
        
        query += " ORDER BY Created DESC"
        
        log_message(f"MANs Query: {query}")
        log_message(f"MANs Params: {params}")
        
        # Executar query com filtros de período aplicados
        df = pd.read_sql(query, conn, params=params)
        
        # Buscar dados para gráficos
        grafico_data = get_mans_chart_data(conn, equipe_filter, periodo_filter, data_inicio, data_fim)
        
        conn.close()
        
        log_message(f"MANs - Registros retornados do banco após filtro de período: {len(df)}")
        
        # Converter datas para string para JSON
        date_columns = ['Created', 'Updated', 'ResolutionDate']
        for col in date_columns:
            if col in df.columns and not df[col].empty:
                try:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
        
        # Converter tipos numpy e retornar dados filtrados por período
        result = convert_numpy_types(df.fillna('').to_dict('records'))
        log_message(f"MANs - Retornando {len(result)} registros (com filtros de período aplicados)")
        
        return jsonify({
            'mans': result,
            'graficos': grafico_data,
            'filtros_aplicados': {
                'equipe': equipe_filter,
                'status': status_filter,
                'produto': produto_filter,
                'periodo': periodo_filter
            }
        })
        
    except Exception as e:
        error_msg = f"Erro na API de MANs: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg})

def get_mans_chart_data(conn, equipe_filter=None, periodo_filter='ano_atual', data_inicio=None, data_fim=None):
    """Função  para obter dados dos gráficos de MANs"""
    try:
        log_message("Obtendo dados dos gráficos de MANs...")
        
        # Calcular datas se não fornecidas
        if not data_inicio or not data_fim:
            data_inicio, data_fim = calculate_period_dates_for_mans(periodo_filter)
            if not data_inicio:
                # Fallback para ano atual se não conseguir calcular
                current_year = datetime.now().year
                data_inicio = f"{current_year}-01-01"
                data_fim = f"{current_year}-12-31"
        
        log_message(f"Período para gráficos: {data_inicio} até {data_fim}")
        
        # 1. Gráfico de backlog por equipe
        query_backlog = """
        SELECT 
            ISNULL(Equipe, 'Sem Equipe') as Equipe,
            COUNT(*) as TotalAbertas,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as TotalFechadas,
            COUNT(*) - SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as Saldo
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        AND Created BETWEEN ? AND ?
        """
        
        params_backlog = [data_inicio, data_fim]
        
        if equipe_filter:
            query_backlog += " AND ISNULL(Equipe, '') = ?"
            params_backlog.append(equipe_filter)
            
        query_backlog += """
        GROUP BY ISNULL(Equipe, 'Sem Equipe')
        ORDER BY Equipe
        """
        
        df_backlog = pd.read_sql(query_backlog, conn, params=params_backlog)
        
        # 2. Tendência mensal
        query_tendencia = """
        SELECT 
            FORMAT(Created, 'yyyy-MM') as Mes,
            COUNT(*) as TotalAbertas,
            SUM(CASE WHEN ResolutionDate IS NOT NULL 
                AND FORMAT(ResolutionDate, 'yyyy-MM') = FORMAT(Created, 'yyyy-MM')
                THEN 1 ELSE 0 END) as FechadasNoMesmo
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        AND Created BETWEEN ? AND ?
        """
        
        params_tendencia = [data_inicio, data_fim]
        
        if equipe_filter:
            query_tendencia += " AND ISNULL(Equipe, '') = ?"
            params_tendencia.append(equipe_filter)
            
        query_tendencia += """
        GROUP BY FORMAT(Created, 'yyyy-MM') 
        ORDER BY FORMAT(Created, 'yyyy-MM')
        """
        
        df_tendencia = pd.read_sql(query_tendencia, conn, params=params_tendencia)
        
        # Processar dados para o frontend
        
        # Dados do backlog (gráfico 1)
        backlog_data = {'equipes': [], 'abertas': [], 'fechadas': [], 'saldo': []}
        if not df_backlog.empty:
            backlog_data = {
                'equipes': df_backlog['Equipe'].tolist(),
                'abertas': df_backlog['TotalAbertas'].astype(int).tolist(),
                'fechadas': df_backlog['TotalFechadas'].astype(int).tolist(),
                'saldo': df_backlog['Saldo'].astype(int).tolist()
            }
        
        # Dados da tendência (gráfico 2)
        tendencia_data = {'meses': [], 'abertas': [], 'fechadas': []}
        if not df_tendencia.empty:
            tendencia_data = {
                'meses': df_tendencia['Mes'].tolist(),
                'abertas': df_tendencia['TotalAbertas'].astype(int).tolist(),
                'fechadas': df_tendencia['FechadasNoMesmo'].astype(int).tolist()
            }
        
        log_message(f"Gráficos MANs - Backlog: {len(backlog_data['equipes'])} equipes, Tendência: {len(tendencia_data['meses'])} meses")
        
        return {
            'backlog': backlog_data,
            'tendencia': tendencia_data,
            'periodo_aplicado': {
                'inicio': data_inicio,
                'fim': data_fim,
                'periodo': periodo_filter
            }
        }
        
    except Exception as e:
        log_message(f"Erro ao obter dados dos gráficos: {e}")
        return {
            'backlog': {'equipes': [], 'abertas': [], 'fechadas': [], 'saldo': []},
            'tendencia': {'meses': [], 'abertas': [], 'fechadas': []},
            'periodo_aplicado': {
                'inicio': data_inicio or '',
                'fim': data_fim or '',
                'periodo': periodo_filter
            }
        }
        
# ===============================
# APIS PARA O DASHBOARD DE MANS
# ===============================
@app.route('/api/mans-table-data')
def mans_table_data_api():
    """API para dados da tabela de MANs com filtros"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        busca_filter = request.args.get('busca', '').strip()
        search_filter = request.args.get('search', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio = request.args.get('data_inicio', '').strip()
        data_fim = request.args.get('data_fim', '').strip()
        
        # Usar busca ou search (compatibilidade)
        search_text = busca_filter or search_filter
        
        log_message(f"MANs Table API - Filtros: equipe={equipe_filter}, status={status_filter}, produto={produto_filter}, busca={search_text}, periodo={periodo_filter}")
        
        # Calcular datas baseadas no período
        if not data_inicio or not data_fim:
            data_inicio, data_fim = calculate_period_dates_for_mans(periodo_filter, data_inicio, data_fim)
        
        # Query base para dados da tabela
        query = """
        SELECT 
            ID,
            ISSUE_ID,
            Number,
            Project,
            ProjectKey,
            IssueType,
            Summary,
            Produto,
            ParentEpicID,
            ParentEpicNumber,
            Equipe,
            Assignee,
            Status,
            Created,
            Updated,
            ResolutionDate,
            OrigemAbertura,
            ServicePackLiberacao,
            PatchLiberacao,
            QtdeVinculos
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        """
        
        params = []
        
        # Aplicar filtros
        if equipe_filter:
            query += " AND ISNULL(Equipe, '') = ?"
            params.append(equipe_filter)
            
        if status_filter:
            query += " AND ISNULL(Status, '') = ?"
            params.append(status_filter)
            
        if produto_filter:
            query += " AND ISNULL(Produto, '') = ?"
            params.append(produto_filter)
        
        # Aplicar filtros de período se tiver
        if data_inicio and data_fim:
            query += " AND Created BETWEEN ? AND ?"
            params.extend([data_inicio, data_fim])
        
        query += " ORDER BY Created DESC"
        
        # Executar query
        df = pd.read_sql(query, conn, params=params)
        log_message(f"MANs Table - {len(df)} registros retornados antes do filtro de busca")
        
        # Aplicar filtro de busca no DataFrame
        if search_text:
            busca_lower = search_text.lower()
            mask = (
                df['Number'].fillna('').astype(str).str.lower().str.contains(busca_lower, na=False) |
                df['Summary'].fillna('').astype(str).str.lower().str.contains(busca_lower, na=False)
            )
            df = df[mask]
            log_message(f"MANs Table - {len(df)} registros após filtro de busca")
        
        # Obter estatísticas usando a função auxiliar
        stats = get_mans_dashboard_stats(conn, equipe_filter, status_filter, produto_filter, periodo_filter, data_inicio, data_fim)
        
        # Converter datas para string
        date_columns = ['Created', 'Updated', 'ResolutionDate']
        for col in date_columns:
            if col in df.columns and not df[col].empty:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Converter para formato JSON
        mans_data = convert_numpy_types(df.fillna('').to_dict('records'))
        
        conn.close()
        
        log_message(f"MANs Table - Retornando {len(mans_data)} registros")
        
        return jsonify({
            'mans': mans_data,
            'stats': stats,
            'filtros_aplicados': {
                'equipe': equipe_filter,
                'status': status_filter,
                'produto': produto_filter,
                'busca': search_text,
                'periodo': periodo_filter
            }
        })
        
    except Exception as e:
        error_msg = f"Erro na API de tabela de MANs: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg})


@app.route('/dashboard-mans')
def dashboard_mans():
    """Página do dashboard de MANs"""
    return render_template('dashboard_mans.html')



def calculate_period_dates_for_mans(periodo_filter, data_inicio_custom=None, data_fim_custom=None):
    """Função auxiliar para calcular datas do período para MANs"""
    today = datetime.now()
    current_year = today.year
    
    if data_inicio_custom and data_fim_custom:
        return data_inicio_custom, data_fim_custom
    
    if periodo_filter == 'ano_atual':
        return f"{current_year}-01-01", f"{current_year}-12-31"
    elif periodo_filter == 'q1':
        return f"{current_year}-01-01", f"{current_year}-03-31"
    elif periodo_filter == 'q2':
        return f"{current_year}-04-01", f"{current_year}-06-30"
    elif periodo_filter == 'q3':
        return f"{current_year}-07-01", f"{current_year}-09-30"
    elif periodo_filter == 'q4':
        return f"{current_year}-10-01", f"{current_year}-12-31"
    elif periodo_filter == '6_meses':
        data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
        data_fim = today.strftime('%Y-%m-%d')
        return data_inicio, data_fim
    elif periodo_filter == '3_meses':
        data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
        data_fim = today.strftime('%Y-%m-%d')
        return data_inicio, data_fim
    elif periodo_filter == 'mes_atual':
        data_inicio = f"{current_year}-{today.month:02d}-01"
        data_fim = today.strftime('%Y-%m-%d')
        return data_inicio, data_fim
    else:
        return None, None

def get_mans_dashboard_stats(conn, equipe_filter=None, status_filter=None, produto_filter=None, 
                           periodo_filter='ano_atual', data_inicio=None, data_fim=None):
    """Função para obter estatísticas completas do dashboard de MANs"""
    try:
        log_message("Obtendo estatísticas do dashboard de MANs...")
        
        # Calcular datas se não fornecidas
        if not data_inicio or not data_fim:
            data_inicio, data_fim = calculate_period_dates_for_mans(periodo_filter)
        
        # Query base com filtros
        where_conditions = ["Project = 'MAN'"]
        params = []
        
        if equipe_filter:
            where_conditions.append("ISNULL(Equipe, '') = ?")
            params.append(equipe_filter)
        
        if status_filter:
            where_conditions.append("ISNULL(Status, '') = ?")
            params.append(status_filter)
        
        if produto_filter:
            where_conditions.append("ISNULL(Produto, '') = ?")
            params.append(produto_filter)
        
        if data_inicio and data_fim:
            where_conditions.append("Created BETWEEN ? AND ?")
            params.extend([data_inicio, data_fim])
        
        where_clause = " AND ".join(where_conditions)
        
        # 1. Estatísticas básicas
        query_stats = f"""
        SELECT 
            COUNT(*) as total_mans,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as mans_fechadas,
            COUNT(*) - SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as mans_abertas,
            COUNT(DISTINCT ISNULL(Equipe, 'Sem Equipe')) as total_equipes,
            AVG(CASE 
                WHEN ResolutionDate IS NOT NULL AND Created IS NOT NULL 
                THEN DATEDIFF(day, Created, ResolutionDate)
                ELSE NULL 
            END) as tempo_medio_resolucao
        FROM BI_Jira_US
        WHERE {where_clause}
        """
        
        df_stats = pd.read_sql(query_stats, conn, params=params)
        stats = convert_numpy_types(df_stats.iloc[0].to_dict()) if not df_stats.empty else {}
        
        # 2. MANs críticas (simulação - você pode ajustar conforme sua regra)
        query_criticas = f"""
        SELECT COUNT(*) as mans_criticas
        FROM BI_Jira_US
        WHERE {where_clause}
        AND (
            DATEDIFF(day, Created, GETDATE()) > 30 OR
            Summary LIKE '%crítico%' OR
            Summary LIKE '%urgente%' OR
            Summary LIKE '%crítica%'
        )
        """
        
        df_criticas = pd.read_sql(query_criticas, conn, params=params)
        if not df_criticas.empty:
            stats['mans_criticas'] = convert_numpy_types(df_criticas.iloc[0]['mans_criticas'])
        else:
            stats['mans_criticas'] = 0
        
        # 3. SLA Atrasado (MANs abertas há mais de X dias)
        query_sla = f"""
        SELECT COUNT(*) as sla_atrasado
        FROM BI_Jira_US
        WHERE {where_clause}
        AND ResolutionDate IS NULL
        AND DATEDIFF(day, Created, GETDATE()) > 15
        """
        
        df_sla = pd.read_sql(query_sla, conn, params=params)
        if not df_sla.empty:
            stats['sla_atrasado'] = convert_numpy_types(df_sla.iloc[0]['sla_atrasado'])
        else:
            stats['sla_atrasado'] = 0
        
        # 4. Backlog total (todas as MANs abertas, independente do período)
        query_backlog = """
        SELECT COUNT(*) as backlog_total
        FROM BI_Jira_US
        WHERE Project = 'MAN'
        AND ResolutionDate IS NULL
        """
        
        backlog_params = []
        if equipe_filter:
            query_backlog += " AND ISNULL(Equipe, '') = ?"
            backlog_params.append(equipe_filter)
        
        df_backlog = pd.read_sql(query_backlog, conn, params=backlog_params)
        if not df_backlog.empty:
            stats['backlog_total'] = convert_numpy_types(df_backlog.iloc[0]['backlog_total'])
        else:
            stats['backlog_total'] = 0
        
        # 5. Taxa de resolução
        total_mans = stats.get('total_mans', 0)
        mans_fechadas = stats.get('mans_fechadas', 0)
        if total_mans > 0:
            stats['taxa_resolucao'] = round((mans_fechadas / total_mans) * 100, 1)
        else:
            stats['taxa_resolucao'] = 0
        
        # Garantir que todos os valores sejam numéricos
        for key in stats:
            if stats[key] is None:
                stats[key] = 0
            elif isinstance(stats[key], float) and pd.isna(stats[key]):
                stats[key] = 0
        
        log_message(f"Estatísticas obtidas: {stats}")
        return stats
        
    except Exception as e:
        log_message(f"Erro ao obter estatísticas do dashboard: {e}")
        return {
            'total_mans': 0,
            'mans_fechadas': 0,
            'mans_abertas': 0,
            'total_equipes': 0,
            'tempo_medio_resolucao': 0,
            'mans_criticas': 0,
            'sla_atrasado': 0,
            'backlog_total': 0,
            'taxa_resolucao': 0
        }
        
    """API para estatísticas do dashboard de MANs com KPIs avançados"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio = request.args.get('data_inicio', '').strip()
        data_fim = request.args.get('data_fim', '').strip()
        
        # Calcular datas baseadas no período
        data_inicio, data_fim = calculate_period_dates_for_mans(periodo_filter, data_inicio, data_fim)
        
        # Query base com filtros
        where_conditions = ["Project = 'MAN'"]
        params = []
        
        if equipe_filter:
            where_conditions.append("ISNULL(Equipe, '') = ?")
            params.append(equipe_filter)
        
        if status_filter:
            where_conditions.append("ISNULL(Status, '') = ?")
            params.append(status_filter)
        
        if produto_filter:
            where_conditions.append("ISNULL(Produto, '') = ?")
            params.append(produto_filter)
        
        if data_inicio and data_fim:
            where_conditions.append("Created BETWEEN ? AND ?")
            params.extend([data_inicio, data_fim])
        
        where_clause = " AND ".join(where_conditions)
        
        # 1. Estatísticas básicas
        query_stats = f"""
        SELECT 
            COUNT(*) as total_mans,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as mans_fechadas,
            COUNT(*) - SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as mans_abertas,
            COUNT(DISTINCT ISNULL(Equipe, 'Sem Equipe')) as total_equipes,
            AVG(CASE 
                WHEN ResolutionDate IS NOT NULL AND Created IS NOT NULL 
                THEN DATEDIFF(day, Created, ResolutionDate)
                ELSE NULL 
            END) as tempo_medio_resolucao
        FROM BI_Jira_US
        WHERE {where_clause}
        """
        
        df_stats = pd.read_sql(query_stats, conn, params=params)
        stats = convert_numpy_types(df_stats.iloc[0].to_dict()) if not df_stats.empty else {}
        
        # 2. MANs críticas (simulação - você pode ajustar conforme sua regra)
        query_criticas = f"""
        SELECT COUNT(*) as mans_criticas
        FROM BI_Jira_US
        WHERE {where_clause}
        AND (
            Priority IN ('High', 'Critical', 'Highest') OR
            DATEDIFF(day, Created, GETDATE()) > 30
        )
        """
        
        df_criticas = pd.read_sql(query_criticas, conn, params=params)
        if not df_criticas.empty:
            stats['mans_criticas'] = convert_numpy_types(df_criticas.iloc[0]['mans_criticas'])
        else:
            stats['mans_criticas'] = 0
        
        # 3. SLA Atrasado (MANs abertas há mais de X dias)
        query_sla = f"""
        SELECT COUNT(*) as sla_atrasado
        FROM BI_Jira_US
        WHERE {where_clause}
        AND ResolutionDate IS NULL
        AND DATEDIFF(day, Created, GETDATE()) > 15
        """
        
        df_sla = pd.read_sql(query_sla, conn, params=params)
        if not df_sla.empty:
            stats['sla_atrasado'] = convert_numpy_types(df_sla.iloc[0]['sla_atrasado'])
        else:
            stats['sla_atrasado'] = 0
        
        # 4. Backlog total (todas as MANs abertas, independente do período)
        query_backlog = """
        SELECT COUNT(*) as backlog_total
        FROM BI_Jira_US
        WHERE Project = 'MAN'
        AND ResolutionDate IS NULL
        """
        
        backlog_params = []
        if equipe_filter:
            query_backlog += " AND ISNULL(Equipe, '') = ?"
            backlog_params.append(equipe_filter)
        
        df_backlog = pd.read_sql(query_backlog, conn, params=backlog_params)
        if not df_backlog.empty:
            stats['backlog_total'] = convert_numpy_types(df_backlog.iloc[0]['backlog_total'])
        else:
            stats['backlog_total'] = 0
        
        # 5. Taxa de resolução
        total_mans = stats.get('total_mans', 0)
        mans_fechadas = stats.get('mans_fechadas', 0)
        if total_mans > 0:
            stats['taxa_resolucao'] = (mans_fechadas / total_mans) * 100
        else:
            stats['taxa_resolucao'] = 0
        
        # 6. Dados para gráfico de distribuição por status
        query_status = f"""
        SELECT 
            ISNULL(Status, 'Indefinido') as status,
            COUNT(*) as quantidade
        FROM BI_Jira_US
        WHERE {where_clause}
        GROUP BY Status
        ORDER BY quantidade DESC
        """
        
        df_status = pd.read_sql(query_status, conn, params=params)
        status_distribution = convert_numpy_types(df_status.to_dict('records')) if not df_status.empty else []
        
        # 7. Performance por equipe (para o gráfico de performance)
        query_performance = f"""
        SELECT 
            ISNULL(Equipe, 'Sem Equipe') as equipe,
            COUNT(*) as total,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as resolvidas,
            AVG(CASE 
                WHEN ResolutionDate IS NOT NULL AND Created IS NOT NULL 
                THEN DATEDIFF(day, Created, ResolutionDate)
                ELSE NULL 
            END) as tempo_medio
        FROM BI_Jira_US
        WHERE {where_clause}
        GROUP BY Equipe
        ORDER BY equipe
        """
        
        df_performance = pd.read_sql(query_performance, conn, params=params)
        performance_data = convert_numpy_types(df_performance.to_dict('records')) if not df_performance.empty else []
        
        conn.close()
        
        return jsonify({
            'stats': stats,
            'status_distribution': status_distribution,
            'performance_data': performance_data,
            'periodo_info': {
                'periodo_selecionado': periodo_filter,
                'data_inicio': data_inicio,
                'data_fim': data_fim,
                'descricao': get_periodo_description(periodo_filter)
            }
        })
        
    except Exception as e:
        error_msg = f"Erro na API de estatísticas do dashboard de MANs: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg})

def calculate_period_dates_for_mans(periodo_filter, data_inicio_custom=None, data_fim_custom=None):
    """Função auxiliar para calcular datas do período para MANs"""
    today = datetime.now()
    current_year = today.year
    
    if data_inicio_custom and data_fim_custom:
        return data_inicio_custom, data_fim_custom
    
    if periodo_filter == 'ano_atual':
        return f"{current_year}-01-01", f"{current_year}-12-31"
    elif periodo_filter == 'q1':
        return f"{current_year}-01-01", f"{current_year}-03-31"
    elif periodo_filter == 'q2':
        return f"{current_year}-04-01", f"{current_year}-06-30"
    elif periodo_filter == 'q3':
        return f"{current_year}-07-01", f"{current_year}-09-30"
    elif periodo_filter == 'q4':
        return f"{current_year}-10-01", f"{current_year}-12-31"
    elif periodo_filter == '6_meses':
        data_inicio = (today - timedelta(days=180)).strftime('%Y-%m-%d')
        data_fim = today.strftime('%Y-%m-%d')
        return data_inicio, data_fim
    elif periodo_filter == '3_meses':
        data_inicio = (today - timedelta(days=90)).strftime('%Y-%m-%d')
        data_fim = today.strftime('%Y-%m-%d')
        return data_inicio, data_fim
    elif periodo_filter == 'mes_atual':
        data_inicio = f"{current_year}-{today.month:02d}-01"
        data_fim = today.strftime('%Y-%m-%d')
        return data_inicio, data_fim
    else:
        return None, None

# Função para dados dos gráficos de MANs
def get_mans_chart_data(conn, equipe_filter=None, periodo_filter='ano_atual', data_inicio=None, data_fim=None):
    """Função ATUALIZADA para obter dados dos gráficos de MANs com dados detalhados"""
    try:
        log_message("Obtendo dados dos gráficos de MANs...")
        
        # Calcular datas se não fornecidas
        if not data_inicio or not data_fim:
            data_inicio, data_fim = calculate_period_dates_for_mans(periodo_filter)
            if not data_inicio:
                # Fallback para ano atual se não conseguir calcular
                current_year = datetime.now().year
                data_inicio = f"{current_year}-01-01"
                data_fim = f"{current_year}-12-31"
        
        log_message(f"Período para gráficos: {data_inicio} até {data_fim}")
        
        # 1. Gráfico de backlog por equipe
        query_backlog = """
        SELECT 
            ISNULL(Equipe, 'Sem Equipe') as Equipe,
            COUNT(*) as TotalAbertas,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as TotalFechadas,
            COUNT(*) - SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as Saldo
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        AND Created BETWEEN ? AND ?
        """
        
        params_backlog = [data_inicio, data_fim]
        
        if equipe_filter:
            query_backlog += " AND ISNULL(Equipe, '') = ?"
            params_backlog.append(equipe_filter)
            
        query_backlog += """
        GROUP BY ISNULL(Equipe, 'Sem Equipe')
        ORDER BY Equipe
        """
        
        df_backlog = pd.read_sql(query_backlog, conn, params=params_backlog)
        
        # 2. Tendência mensal
        query_tendencia = """
        SELECT 
            FORMAT(Created, 'yyyy-MM') as Mes,
            COUNT(*) as TotalAbertas,
            SUM(CASE WHEN ResolutionDate IS NOT NULL 
                AND FORMAT(ResolutionDate, 'yyyy-MM') = FORMAT(Created, 'yyyy-MM')
                THEN 1 ELSE 0 END) as FechadasNoMesmo
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        AND Created BETWEEN ? AND ?
        """
        
        params_tendencia = [data_inicio, data_fim]
        
        if equipe_filter:
            query_tendencia += " AND ISNULL(Equipe, '') = ?"
            params_tendencia.append(equipe_filter)
            
        query_tendencia += """
        GROUP BY FORMAT(Created, 'yyyy-MM') 
        ORDER BY FORMAT(Created, 'yyyy-MM')
        """
        
        df_tendencia = pd.read_sql(query_tendencia, conn, params=params_tendencia)
        
        # 3. NOVO: Dados detalhados por equipe e mês para o gráfico detalhado
        query_detalhado = """
        SELECT 
            ISNULL(Equipe, 'Sem Equipe') as Equipe,
            FORMAT(Created, 'yyyy-MM') as MesAno,
            COUNT(*) as TotalAbertas,
            SUM(CASE WHEN ResolutionDate IS NOT NULL 
                AND FORMAT(ResolutionDate, 'yyyy-MM') = FORMAT(Created, 'yyyy-MM')
                THEN 1 ELSE 0 END) as FechadasNoMesmo,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as TotalFechadas
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        AND Created BETWEEN ? AND ?
        """
        
        params_detalhado = [data_inicio, data_fim]
        
        if equipe_filter:
            query_detalhado += " AND ISNULL(Equipe, '') = ?"
            params_detalhado.append(equipe_filter)
            
        query_detalhado += """
        GROUP BY ISNULL(Equipe, 'Sem Equipe'), FORMAT(Created, 'yyyy-MM')
        ORDER BY Equipe, FORMAT(Created, 'yyyy-MM')
        """
        
        df_detalhado = pd.read_sql(query_detalhado, conn, params=params_detalhado)
        
        # Processar dados para o frontend
        
        # Dados do backlog (gráfico 1)
        backlog_data = {'equipes': [], 'abertas': [], 'fechadas': [], 'saldo': []}
        if not df_backlog.empty:
            backlog_data = {
                'equipes': df_backlog['Equipe'].tolist(),
                'abertas': df_backlog['TotalAbertas'].astype(int).tolist(),
                'fechadas': df_backlog['TotalFechadas'].astype(int).tolist(),
                'saldo': df_backlog['Saldo'].astype(int).tolist()
            }
        
        # Dados da tendência (gráfico 2)
        tendencia_data = {'meses': [], 'abertas': [], 'fechadas': []}
        if not df_tendencia.empty:
            tendencia_data = {
                'meses': df_tendencia['Mes'].tolist(),
                'abertas': df_tendencia['TotalAbertas'].astype(int).tolist(),
                'fechadas': df_tendencia['FechadasNoMesmo'].astype(int).tolist()
            }
        
        # Dados detalhados por equipe e mês (gráfico 5 - NOVO)
        equipe_mes_data = []
        if not df_detalhado.empty:
            equipe_mes_data = convert_numpy_types(df_detalhado.to_dict('records'))
        
        log_message(f"Gráficos MANs - Backlog: {len(backlog_data['equipes'])} equipes, Tendência: {len(tendencia_data['meses'])} meses, Detalhado: {len(equipe_mes_data)} registros")
        
        return {
            'backlog': backlog_data,
            'tendencia': tendencia_data,
            'equipe_mes_detalhado': equipe_mes_data,  # NOVO
            'periodo_aplicado': {
                'inicio': data_inicio,
                'fim': data_fim,
                'periodo': periodo_filter
            }
        }
        
    except Exception as e:
        log_message(f"Erro ao obter dados dos gráficos: {e}")
        return {
            'backlog': {'equipes': [], 'abertas': [], 'fechadas': [], 'saldo': []},
            'tendencia': {'meses': [], 'abertas': [], 'fechadas': []},
            'equipe_mes_detalhado': [],  # NOVO
            'periodo_aplicado': {
                'inicio': data_inicio or '',
                'fim': data_fim or '',
                'periodo': periodo_filter
            }
        }

# mans-data-charts  
@app.route('/api/mans-data-charts')
def mans_data_charts():
    """API ATUALIZADA para dados dos gráficos de MANs"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio = request.args.get('data_inicio', '').strip()
        data_fim = request.args.get('data_fim', '').strip()
        
        log_message(f"MANs Charts API - Filtros: equipe={equipe_filter}, periodo={periodo_filter}")
        
        # Obter dados dos gráficos
        grafico_data = get_mans_chart_data(conn, equipe_filter, periodo_filter, data_inicio, data_fim)
        
        conn.close()
        
        log_message(f"MANs Charts - Dados obtidos: backlog={len(grafico_data.get('backlog', {}).get('equipes', []))}, tendencia={len(grafico_data.get('tendencia', {}).get('meses', []))}")
        
        return jsonify({
            'graficos': grafico_data,
            'filtros_aplicados': {
                'equipe': equipe_filter,
                'periodo': periodo_filter
            }
        })
        
    except Exception as e:
        error_msg = f"Erro na API de gráficos de MANs: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg})
      
# ===============================
# EXPORTAÇÃO DE MANS
# ===============================

@app.route('/export/mans-filtered')  
def export_mans_filtered():
    """ATUALIZADA - Exportar dados de MANs para CSV com filtros aplicados"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        produto_filter = request.args.get('produto', '').strip()
        busca_filter = request.args.get('busca', '').strip()
        search_filter = request.args.get('search', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        data_inicio_custom = request.args.get('data_inicio', '').strip()
        data_fim_custom = request.args.get('data_fim', '').strip()
        total_registros = request.args.get('total_registros', '0')
        
        # Usar busca ou search (compatibilidade)
        search_text = busca_filter or search_filter
        
        log_message(f"Export MANs - Filtros: equipe={equipe_filter}, status={status_filter}, produto={produto_filter}, busca={search_text}, periodo={periodo_filter}, total_registros={total_registros}")
        
        # Calcular datas baseadas no período 
        data_inicio, data_fim = calculate_period_dates_for_mans(periodo_filter, data_inicio_custom, data_fim_custom)
        
        # Query para exportação com colunas formatadas para CSV
        query = """
        SELECT 
            Number as 'Número MAN',
            Summary as 'Resumo',
            ISNULL(Equipe, 'Sem Equipe') as 'Equipe',
            ISNULL(Status, 'Indefinido') as 'Status',
            ISNULL(Produto, 'Sem Produto') as 'Produto',
            ISNULL(Assignee, 'Não Atribuído') as 'Responsável',
            FORMAT(Created, 'dd/MM/yyyy HH:mm') as 'Data Criação',
            FORMAT(Updated, 'dd/MM/yyyy HH:mm') as 'Última Atualização',
            FORMAT(ResolutionDate, 'dd/MM/yyyy HH:mm') as 'Data Resolução',
            CASE 
                WHEN ResolutionDate IS NOT NULL AND Created IS NOT NULL 
                THEN DATEDIFF(day, Created, ResolutionDate)
                ELSE NULL 
            END as 'Tempo Resolução (Dias)',
            ISNULL(OrigemAbertura, 'Não Informada') as 'Origem Abertura',
            ISNULL(ServicePackLiberacao, 'N/A') as 'Service Pack',
            ISNULL(PatchLiberacao, 'N/A') as 'Patch',
            ISNULL(QtdeVinculos, 0) as 'Quantidade Vínculos',
            ISNULL(ProjectKey, 'N/A') as 'Chave Projeto',
            ISNULL(IssueType, 'N/A') as 'Tipo Issue',
            CASE 
                WHEN ResolutionDate IS NOT NULL THEN 'Resolvida'
                WHEN Status IN ('Closed', 'Done', 'Resolved') THEN 'Fechada'
                WHEN Status IN ('In Progress', 'Development') THEN 'Em Andamento'
                ELSE 'Aberta'
            END as 'Situação'
        FROM BI_Jira_US 
        WHERE Project = 'MAN'
        """
        
        params = []
        
        # Aplicar filtros na query (performance)
        if equipe_filter:
            query += " AND ISNULL(Equipe, '') = ?"
            params.append(equipe_filter)
            
        if status_filter:
            query += " AND ISNULL(Status, '') = ?"
            params.append(status_filter)
            
        if produto_filter:
            query += " AND ISNULL(Produto, '') = ?"
            params.append(produto_filter)
        
        # Aplicar filtros de período
        if data_inicio and data_fim:
            query += " AND Created BETWEEN ? AND ?"
            params.extend([data_inicio, data_fim])
        elif data_inicio:
            query += " AND Created >= ?"
            params.append(data_inicio)
        elif data_fim:
            query += " AND Created <= ?"
            params.append(data_fim)
            
        query += " ORDER BY Created DESC"
        
        log_message(f"Query de export MANs: {query}")
        log_message(f"Parâmetros: {params}")
        
        # Executar query
        df = pd.read_sql(query, conn, params=params)
        log_message(f"MANs Export - Registros retornados antes do filtro de busca: {len(df)}")
        
        # Aplicar filtro de busca no DataFrame (igual ao frontend)
        if search_text:
            busca_lower = search_text.lower()
            mask = (
                df['Número MAN'].fillna('').astype(str).str.lower().str.contains(busca_lower, na=False) |
                df['Resumo'].fillna('').astype(str).str.lower().str.contains(busca_lower, na=False)
            )
            df = df[mask]
            log_message(f"MANs Export - Registros após filtro de busca '{search_text}': {len(df)}")
        
        conn.close()
        
        # Verificar se há dados para exportar
        if df.empty:
            log_message("Nenhum dado encontrado para exportar MANs com os filtros aplicados")
            return jsonify({
                'error': 'Nenhum dado encontrado para exportar com os filtros aplicados'
            }), 404
        
        # Preencher valores nulos com texto vazio
        df = df.fillna('')
        
        # Criar arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False)
        
        # Salvar com encoding UTF-8 com BOM para Excel (separador ponto e vírgula)
        df.to_csv(temp_file.name, index=False, encoding='utf-8-sig', sep=';')
        
        # Construir nome do arquivo com informações sobre os filtros
        filename_parts = ['relatorio_mans']
        
        if equipe_filter:
            equipe_clean = equipe_filter.replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename_parts.append(f"equipe_{equipe_clean}")
            
        if status_filter:
            status_clean = status_filter.replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename_parts.append(f"status_{status_clean}")
            
        if produto_filter:
            produto_clean = produto_filter.replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename_parts.append(f"produto_{produto_clean}")
            
        if search_text:
            search_clean = search_text.replace(' ', '_').replace('/', '_').replace('\\', '_')[:10]  # Limitar tamanho
            filename_parts.append(f"busca_{search_clean}")
            
        if periodo_filter and periodo_filter != 'ano_atual':
            filename_parts.append(f"periodo_{periodo_filter}")
            
        if data_inicio or data_fim:
            if data_inicio and data_fim:
                filename_parts.append(f"{data_inicio}_a_{data_fim}")
            elif data_inicio:
                filename_parts.append(f"desde_{data_inicio}")
            elif data_fim:
                filename_parts.append(f"ate_{data_fim}")
        
        # Adicionar timestamp e total de registros
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_parts.append(f"{len(df)}registros")
        filename_parts.append(timestamp)
        
        filename = '_'.join(filename_parts) + '.csv'
        
        # Limitar tamanho do nome do arquivo (Windows tem limite de 255 chars)
        if len(filename) > 200:
            filename = f"relatorio_mans_{len(df)}registros_{timestamp}.csv"
        
        log_message(f"Exportando MANs - {len(df)} registros para arquivo: {filename}")
        
        return send_file(temp_file.name, 
                        as_attachment=True, 
                        download_name=filename,
                        mimetype='text/csv')
        
    except Exception as e:
        error_msg = f"Erro na exportação de MANs: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg}), 500


# ===============================
# APIS AUXILIARES PARA MANS
# ===============================

@app.route('/api/mans-filters')
def mans_filters():
    """API para obter opções de filtros específicas para MANs"""
    try:
        conn = db_manager.get_connection()
        
        # Buscar equipes distintas de MANs
        query_equipes = """
        SELECT DISTINCT ISNULL(Equipe, 'Sem Equipe') as equipe
        FROM BI_Jira_US
        WHERE Project = 'MAN' AND Equipe IS NOT NULL AND Equipe != ''
        ORDER BY equipe
        """
        df_equipes = pd.read_sql(query_equipes, conn)
        equipes = df_equipes['equipe'].tolist() if not df_equipes.empty else []
        
        # Buscar produtos distintos de MANs
        query_produtos = """
        SELECT DISTINCT ISNULL(Produto, 'Sem Produto') as produto
        FROM BI_Jira_US
        WHERE Project = 'MAN' AND Produto IS NOT NULL AND Produto != ''
        ORDER BY produto
        """
        df_produtos = pd.read_sql(query_produtos, conn)
        produtos = df_produtos['produto'].tolist() if not df_produtos.empty else []
        
        # Buscar status distintos de MANs
        query_status = """
        SELECT DISTINCT ISNULL(Status, 'Indefinido') as status
        FROM BI_Jira_US
        WHERE Project = 'MAN' AND Status IS NOT NULL AND Status != ''
        ORDER BY status
        """
        df_status = pd.read_sql(query_status, conn)
        status = df_status['status'].tolist() if not df_status.empty else []
        
        conn.close()
        
        return jsonify({
            'equipes': equipes,
            'produtos': produtos,
            'status': status
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/mans-insights')
def mans_insights():
    """API para insights e análises avançadas de MANs"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros
        equipe_filter = request.args.get('equipe', '').strip()
        periodo_filter = request.args.get('periodo', 'ano_atual')
        
        data_inicio, data_fim = calculate_period_dates_for_mans(periodo_filter)
        
        # Análise 1: Top 5 equipes com melhor performance
        query_top_equipes = """
        SELECT TOP 5
            ISNULL(Equipe, 'Sem Equipe') as equipe,
            COUNT(*) as total_mans,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as resolvidas,
            CASE 
                WHEN COUNT(*) > 0 
                THEN (SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*))
                ELSE 0 
            END as taxa_resolucao,
            AVG(CASE 
                WHEN ResolutionDate IS NOT NULL AND Created IS NOT NULL 
                THEN DATEDIFF(day, Created, ResolutionDate)
                ELSE NULL 
            END) as tempo_medio
        FROM BI_Jira_US
        WHERE Project = 'MAN'
        AND Created BETWEEN ? AND ?
        GROUP BY Equipe
        HAVING COUNT(*) >= 5
        ORDER BY taxa_resolucao DESC, tempo_medio ASC
        """
        
        df_top = pd.read_sql(query_top_equipes, conn, params=[data_inicio, data_fim])
        top_equipes = convert_numpy_types(df_top.to_dict('records')) if not df_top.empty else []
        
        # Análise 2: Tendência comparativa (período atual vs anterior)
        if periodo_filter == 'ano_atual':
            today = datetime.now()
            ano_anterior = today.year - 1
            data_inicio_anterior = f"{ano_anterior}-01-01"
            data_fim_anterior = f"{ano_anterior}-12-31"
        else:
            # Para outros períodos, calcular período equivalente anterior
            try:
                delta = datetime.strptime(data_fim, '%Y-%m-%d') - datetime.strptime(data_inicio, '%Y-%m-%d')
                data_fim_anterior = (datetime.strptime(data_inicio, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
                data_inicio_anterior = (datetime.strptime(data_inicio, '%Y-%m-%d') - delta - timedelta(days=1)).strftime('%Y-%m-%d')
            except:
                data_inicio_anterior = data_inicio
                data_fim_anterior = data_fim
        
        query_comparacao = """
        SELECT 
            'atual' as periodo,
            COUNT(*) as total_mans,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as resolvidas
        FROM BI_Jira_US
        WHERE Project = 'MAN' AND Created BETWEEN ? AND ?
        UNION ALL
        SELECT 
            'anterior' as periodo,
            COUNT(*) as total_mans,
            SUM(CASE WHEN ResolutionDate IS NOT NULL THEN 1 ELSE 0 END) as resolvidas
        FROM BI_Jira_US
        WHERE Project = 'MAN' AND Created BETWEEN ? AND ?
        """
        
        df_comp = pd.read_sql(query_comparacao, conn, params=[data_inicio, data_fim, data_inicio_anterior, data_fim_anterior])
        comparacao = convert_numpy_types(df_comp.to_dict('records')) if not df_comp.empty else []
        
        conn.close()
        
        return jsonify({
            'top_equipes': top_equipes,
            'comparacao_periodo': comparacao,
            'periodo_atual': {
                'inicio': data_inicio,
                'fim': data_fim
            },
            'periodo_anterior': {
                'inicio': data_inicio_anterior,
                'fim': data_fim_anterior
            }
        })
        
    except Exception as e:
        error_msg = f"Erro na API de insights de MANs: {str(e)}"
        log_message(error_msg)
        return jsonify({'error': error_msg})

# ===============================
# ATUALIZAÇÃO DAS ROTAS EXISTENTES
# ===============================

# Certificar-se de que as rotas já existentes não entrem em conflito
# Caso você já tenha algumas dessas rotas implementadas, compare e ajuste conforme necessário

# Função para limpeza de arquivos temporários
def cleanup_temp_files():
    """Limpar arquivos temporários antigos"""
    try:
        import glob
        import time
        temp_pattern = os.path.join(tempfile.gettempdir(), "tmp*.csv")
        for temp_file in glob.glob(temp_pattern):
            try:
                # Deletar arquivos temporários com mais de 1 hora
                if time.time() - os.path.getctime(temp_file) > 3600:
                    os.unlink(temp_file)
            except:
                pass
    except:
        pass

# Adicionar limpeza de arquivos temporários na inicialização
# cleanup_temp_files()

def open_browser():
    """Abre o navegador após iniciar o servidor"""
    webbrowser.open_new('http://localhost:5000/')

if __name__ == '__main__':
    # Configurar para não mostrar console no executável
    if getattr(sys, 'frozen', False):
        # Executando como .exe
        threading.Timer(1.5, open_browser).start()
        app.run(host='localhost', port=5000, debug=False, use_reloader=False)
    else:
        # Executando como script Python
        threading.Timer(1.5, open_browser).start()
        app.run(host='localhost', port=5000, debug=True)