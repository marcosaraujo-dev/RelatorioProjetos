import os
import sys
import webbrowser
import threading
from datetime import datetime
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

@app.route('/api/dashboard-data')
def dashboard_data():
    """API para dados do dashboard com filtros"""
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
        
        conn.close()
        
        return jsonify({
            'stats': stats,
            'equipes': equipes,
            'timeline': [],  # Pode ser implementado depois se necessário
            'filtros_aplicados': {
                'equipe': equipe_filter,
                'produto': produto_filter,
                'status': status_filter,
                'periodo': periodo_filter
            }
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
def gantt_data():
    """API para dados do gráfico de Gantt - VERSÃO CORRIGIDA"""
    try:
        log_message("=== INICIANDO GANTT-DATA CORRIGIDO ===")
        
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
        data_inicio = request.args.get('data_inicio', '2025-01-01')
        data_fim = request.args.get('data_fim', '2025-12-31')
        
        if not data_inicio:
            data_inicio = '2025-01-01'
        if not data_fim:
            data_fim = '2025-12-31'
        
        log_message(f"Filtros: equipe='{equipe_filter}', status='{status_filter}', inicio='{data_inicio}', fim='{data_fim}'")
        
        # Query com lógica correta de filtro de período
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
            CAST(ISNULL(IndicadorAndamentoEpico, '') AS VARCHAR(100)) as IndicadorAndamentoEpico
        FROM BI_Jira_Epico_Datas_Grafico
        WHERE EpicInicioPlanejado IS NOT NULL 
        AND EpicDueDate IS NOT NULL
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
            
        query += " ORDER BY EpicEquipe, EpicInicioPlanejado"
        
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
        
        # Processar dados para o Gantt
        gantt_data = []
        
        log_message("Processando dados...")
        
        for index, row in df.iterrows():
            try:
                log_message(f"Processando linha {index + 1}/{len(df)}")
                
                epic_number = str(row['EpicNumber']) if row['EpicNumber'] is not None else f"Epic-{index}"
                epic_summary = str(row['EpicSummary']) if row['EpicSummary'] is not None else "Sem resumo"
                epic_equipe = str(row['EpicEquipe']) if row['EpicEquipe'] is not None else "Sem Equipe"
                
                if len(epic_summary) > 60:
                    epic_summary = epic_summary[:60] + "..."
                
                # Datas planejadas (Epic)
                planned_start = row['EpicInicioPlanejado']
                planned_finish = row['EpicDueDate']
                
                # Datas executadas (Tasks)
                actual_start = row['TasksDataInicial'] if pd.notna(row['TasksDataInicial']) else planned_start
                actual_finish = row['TasksDataFim'] if pd.notna(row['TasksDataFim']) else planned_finish
                
                if pd.isna(planned_start) or pd.isna(planned_finish):
                    log_message(f"  Pulando linha {index} - datas planejadas inválidas")
                    continue
                
                task_name = f"{epic_number} - {epic_summary}"
                
                # Determinar se está atrasado (comparando data atual com data planejada)
                hoje = datetime.now().date()
                prazo_estourado = False
                
                if pd.notna(planned_finish):
                    if isinstance(planned_finish, str):
                        planned_finish_date = datetime.strptime(planned_finish, '%Y-%m-%d').date()
                    else:
                        planned_finish_date = planned_finish.date()
                    
                    if hoje > planned_finish_date and row['EpicStatus'] not in ['Done', 'Closed']:
                        prazo_estourado = True
                
                gantt_data.append({
                    'Task': task_name,
                    'PlannedStart': planned_start.strftime('%Y-%m-%d') if pd.notna(planned_start) else None,
                    'PlannedFinish': planned_finish.strftime('%Y-%m-%d') if pd.notna(planned_finish) else None,
                    'ActualStart': actual_start.strftime('%Y-%m-%d') if pd.notna(actual_start) else None,
                    'ActualFinish': actual_finish.strftime('%Y-%m-%d') if pd.notna(actual_finish) else None,
                    'Resource': epic_equipe,
                    'Complete': float(row['TasksPercentualMedia']) if pd.notna(row['TasksPercentualMedia']) else 0.0,
                    'Status': str(row['EpicStatus']),
                    'PrazoEstourado': prazo_estourado
                })
                
                log_message(f"  Linha {index + 1} processada com sucesso")
                
            except Exception as e:
                log_message(f"ERRO na linha {index}: {e}")
                continue
        
        log_message(f"Total processado: {len(gantt_data)} itens")
        
        if not gantt_data:
            return jsonify({
                'message': 'Nenhum épico com datas válidas encontrado',
                'equipes': [],
                'status': [],
                'total_epicos': 0
            })
        
        # Criar gráfico Plotly CORRIGIDO
        log_message("Criando gráfico Plotly corrigido...")
        
        fig = go.Figure()
        
        log_message(f"Total de itens no gantt_data: {len(gantt_data)}")
        
        # Controle de legendas por status
        legendas_mostradas = {
            'Planejado': False,
            'Concluído': False,
            'Em Andamento': False,
            'Atrasado': False
        }
        
        # Criar traces para cada item
        for i, item in enumerate(gantt_data):
            
            # === BARRA PLANEJADA (cinza transparente) ===
            if item['PlannedStart'] and item['PlannedFinish']:
                show_legend = not legendas_mostradas['Planejado']
                legendas_mostradas['Planejado'] = True
                
                fig.add_trace(go.Scatter(
                    x=[item['PlannedStart'], item['PlannedFinish']],
                    y=[item['Task'], item['Task']],
                    mode='lines',
                    line=dict(
                        color='#6c757d',  # Cinza
                        width=20
                    ),
                    opacity=0.4,
                    name='Planejado',
                    showlegend=show_legend,
                    legendgroup='planejado',
                    hovertemplate=(
                        '<b>PLANEJADO</b><br>' +
                        '<b>%{text}</b><br>' +
                        'Equipe: ' + str(item["Resource"]) + '<br>' +
                        'Início Planejado: ' + str(item["PlannedStart"]) + '<br>' +
                        'Fim Planejado: ' + str(item["PlannedFinish"]) + '<br>' +
                        'Status: ' + str(item["Status"]) + '<br>' +
                        '<extra></extra>'
                    ),
                    text=[item['Task'], item['Task']],
                    hoverinfo='text'
                ))
            
            # === BARRA EXECUTADA/REAL (cores por status) ===
            if item['ActualStart'] and item['ActualFinish']:
                
                # DEBUG: Log do status para verificar a lógica
                log_message(f"Item {i}: Status='{item['Status']}', PrazoEstourado={item['PrazoEstourado']}")
                
                # LÓGICA CORRIGIDA: Verificar primeiro se está concluído
                status_upper = item['Status'].upper()
                
                if status_upper in ['DONE', 'CLOSED', 'CONCLUÍDO', 'FINALIZADO']:
                    color = '#28a745'  # Verde - Concluído
                    status_label = 'Concluído'
                    status_text = "CONCLUÍDO"
                elif item['PrazoEstourado']:
                    color = '#dc3545'  # Vermelho - Atrasado
                    status_label = 'Atrasado'
                    status_text = "ATRASADO"
                else:
                    # Todos os outros casos: em andamento
                    color = '#ffc107'  # Amarelo - Em Andamento
                    status_label = 'Em Andamento'
                    status_text = "EM ANDAMENTO"
                
                log_message(f"  -> Cor escolhida: {color} ({status_label})")
                
                show_legend = not legendas_mostradas[status_label]
                legendas_mostradas[status_label] = True
                
                fig.add_trace(go.Scatter(
                    x=[item['ActualStart'], item['ActualFinish']],
                    y=[item['Task'], item['Task']],
                    mode='lines',
                    line=dict(
                        color=color,
                        width=30  # Mais grossa
                    ),
                    opacity=1.0,
                    name=status_label,
                    showlegend=show_legend,
                    legendgroup=status_label.lower().replace(' ', '_'),
                    hovertemplate=(
                        f'<b>{status_text}</b><br>' +
                        '<b>%{text}</b><br>' +
                        'Equipe: ' + str(item["Resource"]) + '<br>' +
                        'Início Real: ' + str(item["ActualStart"]) + '<br>' +
                        'Fim Real: ' + str(item["ActualFinish"]) + '<br>' +
                        'Progresso: ' + str(item["Complete"]) + '%<br>' +
                        'Status Original: ' + str(item["Status"]) + '<br>' +
                        '<extra></extra>'
                    ),
                    text=[item['Task'], item['Task']],
                    hoverinfo='text'
                ))
        
        log_message(f"Total de traces adicionadas: {len(fig.data)}")
        
        # Calcular range de datas para zoom inicial correto
        all_dates = []
        for item in gantt_data:
            if item['PlannedStart']:
                all_dates.append(datetime.strptime(item['PlannedStart'], '%Y-%m-%d'))
            if item['PlannedFinish']:
                all_dates.append(datetime.strptime(item['PlannedFinish'], '%Y-%m-%d'))
            if item['ActualStart']:
                all_dates.append(datetime.strptime(item['ActualStart'], '%Y-%m-%d'))
            if item['ActualFinish']:
                all_dates.append(datetime.strptime(item['ActualFinish'], '%Y-%m-%d'))
        
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
        
        # Adicionar linha vertical "HOJE" usando add_shape
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
        
        # Configurar layout CORRIGIDO - RESPONSIVO E OCUPANDO TODA LARGURA
        fig.update_layout(
            title={
                'text': 'Cronograma de Épicos - Gráfico de Gantt<br><sub>Verde=Concluído | Amarelo=Em Andamento | Vermelho=Atrasado | Cinza=Planejado</sub>',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16}
            },
            
            # Altura baseada no número de itens
            height=max(700, len(gantt_data) * 60 + 200),
            # REMOVER WIDTH FIXO para ocupar toda div
            
            # EIXO X PRINCIPAL (inferior) - SEM AUTORANGE
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
                # FORÇAR RANGE AQUI
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
            
            # EIXO Y
            yaxis=dict(
                autorange='reversed',
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                tickfont=dict(size=10),
                side='left',
                showline=True,
                linewidth=2,
                linecolor='black',
                title=dict(text='Épicos', font=dict(size=14))
            ),
            
            # MARGENS OTIMIZADAS
            margin=dict(l=400, r=50, t=180, b=120),
            
            # CORES E FONTES
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family="Arial, sans-serif", size=12),
            
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
            
            # CONFIGURAÇÕES RESPONSIVAS CORRETAS
            autosize=True  # Mudança principal: TRUE para ocupar toda div
        )
        
        log_message("Layout configurado! Convertendo para JSON...")
        
        graphJSON = json.dumps(fig, cls=PlotlyJSONEncoder)
        
        # Obter listas para filtros
        equipes_list = sorted(df['EpicEquipe'].dropna().unique().tolist())
        status_list = sorted(df['EpicStatus'].dropna().unique().tolist())
        
        log_message(f"SUCESSO! Retornando {len(df)} épicos")
        log_message("=== FIM GANTT-DATA CORRIGIDO ===")
        
        return jsonify({
            'gantt': graphJSON,
            'equipes': equipes_list,
            'status': status_list,
            'total_epicos': len(df)
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