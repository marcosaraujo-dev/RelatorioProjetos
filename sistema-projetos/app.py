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

# Configurar logging para capturar tudo
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = 'sistema_projetos_empresa_2025_web_key'

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
        """
        
        df_stats = pd.read_sql(query_stats, conn)
        if not df_stats.empty:
            stats = convert_numpy_types(df_stats.iloc[0].to_dict())
            for key in default_stats:
                if key not in stats or stats[key] is None:
                    stats[key] = default_stats[key]
        else:
            stats = default_stats
        
        # CORREÇÃO: Adicionar contagens de alertas específicos
        # Épicos que vencem nos próximos 7 dias
        query_proximo = """
        SELECT COUNT(*) as count_proximo
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicInicioPlanejado IS NOT NULL
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
        
        # CORREÇÃO: Adicionar contagens específicas para alertas
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
        
        # CORREÇÃO: Adicionar contagens específicas para alertas
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

@app.route('/logs')
def view_logs():
    """Visualizar logs da aplicação"""
    logs_html = "<h2>Logs da Aplicação</h2>"
    logs_html += "<div style='background: #f8f9fa; padding: 15px; border: 1px solid #ddd; max-height: 500px; overflow-y: scroll;'>"
    
    if app_logs:
        for log in app_logs[-50:]:
            logs_html += f"<div style='font-family: monospace; margin: 2px 0;'>{log}</div>"
    else:
        logs_html += "<div>Nenhum log ainda. Acesse o Gantt para gerar logs.</div>"
    
    logs_html += "</div>"
    logs_html += "<br><a href='/gantt'>← Voltar ao Gantt</a>"
    logs_html += "<br><a href='/logs'>🔄 Atualizar Logs</a>"
    
    return logs_html

@app.route('/api/gantt-data')
@app.route('/api/gantt-data')
def gantt_data():
    """API para dados do gráfico de Gantt AGRUPADO POR ÉPICO"""
    try:
        log_message("=== INICIANDO GANTT-DATA AGRUPADO ===")
        
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
        
        # Query MODIFICADA para buscar todos os tipos de registro por épico
        query = """
        SELECT 
            CAST(ISNULL(EpicNumber, 'Epic-0') AS VARCHAR(50)) as EpicNumber,
            CAST(ISNULL(EpicSummary, 'Sem resumo') AS VARCHAR(500)) as EpicSummary,
            CAST(ISNULL(EpicEquipe, 'Sem Equipe') AS VARCHAR(100)) as EpicEquipe,
            CAST(ISNULL(EpicStatus, 'Indefinido') AS VARCHAR(50)) as EpicStatus,
            EpicInicioPlanejado,
            EpicDueDate,
            TasksDataInicial,
            TasksDataFim,
            CAST(ISNULL(TasksPercentualMedia, 0) AS DECIMAL(5,2)) as TasksPercentualMedia,
            CAST(ISNULL(IndicadorAndamentoEpico, '') AS VARCHAR(100)) as IndicadorAndamentoEpico,
            CAST(ISNULL(TipoRegistroCalculo, 'Indefinido') AS VARCHAR(50)) as TipoRegistroCalculo
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
                epic_summary_str = str(epic_summary) if epic_summary is not None else "Sem resumo"
                epic_equipe_str = str(epic_equipe) if epic_equipe is not None else "Sem Equipe"
                
                if len(epic_summary_str) > 60:
                    epic_summary_str = epic_summary_str[:60] + "..."
                
                # Base do nome da task (épico)
                task_base_name = f"{epic_number_str} - {epic_summary_str}"
                
                # Determinar se está atrasado (comparando data atual com data planejada)
                hoje = datetime.now().date()
                prazo_estourado = False
                
                # Pegar a data de término do planejamento do PO (primeira linha do grupo)
                primeira_linha = grupo.iloc[0]
                planned_finish = primeira_linha['EpicDueDate']
                
                if pd.notna(planned_finish):
                    if isinstance(planned_finish, str):
                        planned_finish_date = datetime.strptime(planned_finish, '%Y-%m-%d').date()
                    else:
                        planned_finish_date = planned_finish.date()
                    
                    if hoje > planned_finish_date and epic_status not in ['Done', 'Closed']:
                        prazo_estourado = True
                
                # Processar cada tipo de registro (Planejado P.O., Planejado Time, Realizado Time)
                for index, row in grupo.iterrows():
                    tipo_registro = row['TipoRegistroCalculo']
                    
                    # Definir o nome da subtask baseado no tipo
                    if tipo_registro == 'Planejado P.O.':
                        task_name = f"  📋 PO: {task_base_name}"
                        color = '#6c757d'  # Cinza - Planejamento do PO
                        opacity = 0.6
                        width = 15
                    elif tipo_registro == 'Planejado Time':
                        task_name = f"  ⏰ Time: {task_base_name}"
                        color = '#17a2b8'  # Azul - Planejamento do Time
                        opacity = 0.8
                        width = 20
                    elif tipo_registro == 'Realizado Time':
                        task_name = f"  ✅ Real: {task_base_name}"
                        # Cor baseada no status
                        if epic_status.upper() in ['DONE', 'CLOSED', 'CONCLUÍDO', 'FINALIZADO']:
                            color = '#28a745'  # Verde - Concluído
                        elif prazo_estourado:
                            color = '#dc3545'  # Vermelho - Atrasado
                        else:
                            color = '#ffc107'  # Amarelo - Em Andamento
                        opacity = 1.0
                        width = 25
                    else:
                        continue  # Pular tipos não reconhecidos
                    
                    # Datas de início e fim
                    task_start = row['TasksDataInicial']
                    task_finish = row['TasksDataFim']
                    
                    if pd.isna(task_start) or pd.isna(task_finish):
                        log_message(f"  Pulando {tipo_registro} - datas inválidas")
                        continue
                    
                    gantt_data.append({
                        'Task': task_name,
                        'Start': task_start.strftime('%Y-%m-%d') if pd.notna(task_start) else None,
                        'Finish': task_finish.strftime('%Y-%m-%d') if pd.notna(task_finish) else None,
                        'Resource': epic_equipe_str,
                        'Complete': float(row['TasksPercentualMedia']) if pd.notna(row['TasksPercentualMedia']) else 0.0,
                        'Status': str(epic_status),
                        'TipoRegistro': tipo_registro,
                        'EpicNumber': epic_number_str,
                        'PrazoEstourado': prazo_estourado,
                        'Color': color,
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
        
        # Criar gráfico Plotly com AGRUPAMENTO
        log_message("Criando gráfico Plotly agrupado...")
        
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
            
            # Nome para a legenda
            legend_name = {
                'Planejado P.O.': 'Planejado P.O.',
                'Planejado Time': 'Planejado Time',
                'Realizado Time': 'Realizado Time'
            }.get(tipo_registro, tipo_registro)
            
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
                hovertemplate=(
                    f'<b>{tipo_registro.upper()}</b><br>' +
                    '<b>%{text}</b><br>' +
                    'Equipe: ' + str(item["Resource"]) + '<br>' +
                    'Início: ' + str(item["Start"]) + '<br>' +
                    'Fim: ' + str(item["Finish"]) + '<br>' +
                    'Progresso: ' + str(item["Complete"]) + '%<br>' +
                    'Status: ' + str(item["Status"]) + '<br>' +
                    '<extra></extra>'
                ),
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
                'text': 'Roadmap de Épicos - Gráfico de Gantt Agrupado<br><sub>📋 PO=Planejado PO | ⏰ Time=Planejado Time | ✅ Real=Realizado Time</sub>',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16}
            },
            
            # Altura baseada no número de itens (considerando agrupamento)
            height=max(800, len(gantt_data) * 35 + 200),
            
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
                title=dict(text='Épicos por Tipo', font=dict(size=14))
            ),
            
            # MARGENS OTIMIZADAS para agrupamento
            margin=dict(l=450, r=50, t=180, b=120),
            
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
        
        graphJSON = json.dumps(fig, cls=PlotlyJSONEncoder)
        
        # Obter listas para filtros (únicas)
        equipes_list = sorted(df['EpicEquipe'].dropna().unique().tolist())
        status_list = sorted(df['EpicStatus'].dropna().unique().tolist())
        
        # Contar épicos únicos
        total_epicos_unicos = df['EpicNumber'].nunique()
        
        log_message(f"SUCESSO! Retornando {total_epicos_unicos} épicos únicos com {len(gantt_data)} registros")
        log_message("=== FIM GANTT-DATA AGRUPADO ===")
        
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

@app.route('/relatorio-subtasks')
def relatorio_subtasks():
    """Página do relatório de subtasks"""
    return render_template('relatorio_subtasks.html')

@app.route('/api/subtasks-data')
def subtasks_data():
    """API para dados das subtasks"""
    try:
        conn = db_manager.get_connection()
        
        query = """
        SELECT * FROM BI_Jira_SubTasks_Datas_Grafico
        ORDER BY TaskEquipe, TaskNumberId
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Converter datas para string para JSON
        date_columns = [col for col in df.columns if 'date' in col.lower() or 'inicio' in col.lower() or 'fim' in col.lower() or 'created' in col.lower() or 'updated' in col.lower()]
        for col in date_columns:
            if col in df.columns and df[col].dtype == 'datetime64[ns]':
                df[col] = df[col].dt.strftime('%d/%m/%Y %H:%M')
        
        return jsonify(df.fillna('').to_dict('records'))
        
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/export/epicos')
def export_epicos():
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
    """Exportar subtasks para CSV com filtros aplicados"""
    try:
        conn = db_manager.get_connection()
        
        # Obter parâmetros dos filtros
        equipe_filter = request.args.get('equipe', '').strip()
        status_filter = request.args.get('status', '').strip()
        tipo_filter = request.args.get('tipo', '').strip()
        etapa_filter = request.args.get('etapa', '').strip()
        search_filter = request.args.get('search', '').strip()
        data_inicio = request.args.get('data_inicio', '')
        data_fim = request.args.get('data_fim', '')
        
        # Query base
        query = "SELECT * FROM BI_Jira_SubTasks_Datas_Grafico WHERE 1=1"
        params = []
        
        # Aplicar filtros básicos
        if equipe_filter:
            query += " AND ISNULL(TaskEquipe, '') = ?"
            params.append(equipe_filter)
            
        if status_filter:
            query += " AND ISNULL(TaskStatus, '') = ?"
            params.append(status_filter)
            
        if tipo_filter:
            query += " AND ISNULL(TaskType, '') = ?"
            params.append(tipo_filter)
            
        if etapa_filter:
            query += " AND ISNULL(TaskEtapa, '') = ?"
            params.append(etapa_filter)
        
        # Aplicar filtro de data
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
        
        # Executar query
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        # Aplicar filtro de busca (texto) no DataFrame
        if search_filter:
            search_lower = search_filter.lower()
            mask = (
                df['TaskNumberId'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False) |
                df['TaskSummary'].fillna('').astype(str).str.lower().str.contains(search_lower, na=False)
            )
            df = df[mask]
        
        # Criar arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False)
        df.to_csv(temp_file.name, index=False, encoding='utf-8-sig')
        
        # Nome do arquivo com informações sobre os filtros
        filename_parts = ['relatorio_subtasks']
        if equipe_filter:
            filename_parts.append(f"equipe_{equipe_filter.replace(' ', '_')}")
        if status_filter:
            filename_parts.append(f"status_{status_filter.replace(' ', '_')}")
        if tipo_filter:
            filename_parts.append(f"tipo_{tipo_filter.replace(' ', '_')}")
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