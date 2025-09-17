from flask import Flask, render_template, request, g,jsonify

from datetime import date
import sqlite3
from uuid import uuid4
from flask import redirect, url_for, session
import secrets
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import json
import os
import hashlib
import pytz
import pdfkit, os, pytz
from pathlib import Path
from flask import Response
from functools import wraps
from calendar import monthrange
import plotly.graph_objs as go
import plotly.io as pio


# >>> ADD: roles/helpers/decorador
# perfis possíveis: 'admin_geral','admin','denuncias','reclamacoes'
ROLES_DEN = {"admin_geral", "admin", "denuncias"}
ROLES_REC = {"admin_geral", "admin", "reclamacoes"}
# === TIPOS DE RECLAMAÇÃO (grupos) ===
TIPOS_REC_GROUPS = [
    ("1. Questões de Contratação e Integração", [
        ("recrutamento_injusto", "Processo de recrutamento injusto"),
        ("integracao_dificuldades", "Problemas com integração"),
        ("erros_contratos", "Erros em ofertas ou contratos"),
    ]),
    ("2. Condições de Trabalho", [
        ("ambiente_inadequado", "Ambiente físico inadequado"),
        ("infraestrutura_deficiente", "Problemas com infraestrutura"),
    ]),
    ("3. Gestão de Desempenho", [
        ("avaliacao_injusta", "Avaliações injustas"),
        ("falta_feedback", "Falta de feedback"),
        ("metas_mal_definidas", "Problemas com metas"),
    ]),
    ("4. Políticas e Procedimentos", [
        ("politicas_pouco_claras", "Políticas pouco claras"),
        ("politicas_inconsistentes", "Aplicação inconsistente"),
        ("mudancas_sem_aviso", "Mudanças sem comunicação"),
    ]),
    ("5. Relações Interpessoais", [
        ("conflitos_funcionarios", "Conflitos entre funcionários"),
        ("bullying_trabalho", "Bullying no trabalho"),
    ]),
    ("6. Compensação e Benefícios", [
        ("salario", "Discrepâncias salariais"),
        ("beneficios", "Problemas com benefícios"),
        ("bonus", "Questões sobre bônus"),
    ]),
    ("7. Treinamento e Desenvolvimento", [
        ("falta_oportunidades", "Falta de desenvolvimento"),
        ("qualidade_treinamento", "Treinamento de baixa qualidade"),
        ("acesso_limitado", "Acesso limitado a recursos"),
    ]),
    ("8. Horários e Equilíbrio", [
        ("horarios_trabalho", "Horários e turnos"),
        ("vida_pessoal_trabalho", "Equilíbrio vida/trabalho"),
        ("licencas_ferias", "Licenças e férias"),
    ]),
    ("9. Comunicação Interna", [
        ("falta_comunicacao", "Falta de comunicação"),
        ("informacao_dificil_acesso", "Acesso difícil a informação"),
        ("disseminacao_fraca", "Má comunicação interna"),
    ]),
    ("10. Procedimentos Disciplinares", [
        ("medidas_inadequadas", "Medidas inadequadas"),
        ("regras_confusas", "Regras pouco claras"),
        ("processo_injusto", "Processos injustos"),
    ]),
    ("11. Saúde e Segurança (HSEQ)", [
        ("seguranca", "Segurança no trabalho"),
        ("nao_conformidade_normas", "Não cumprimento de normas"),
        ("bem_estar", "Bem‑estar dos funcionários"),
    ]),
    ("12. Outros", [
        ("outros", "Outros / Sugestões"),
    ]),
]



def is_admin():
    return session.get("perfil") in {"admin_geral", "admin"}

def can_denuncias():
    return session.get("perfil") in ROLES_DEN

def can_reclamacoes():
    return session.get("perfil") in ROLES_REC

def require_roles(roles: set[str]):
    def deco(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("perfil") not in roles:
                from flask import abort
                return abort(403)
            return view(*args, **kwargs)
        return wrapped
    return deco
# <<< END ADD



app = Flask(__name__)
DATABASE = "confidencia.db"
app.secret_key = 'segredo-super-seguro-123'
# Pasta para uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'mp3', 'wav', 'm4a', 'ogg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Config extra (no topo, junto com UPLOAD_FOLDER):
AVATAR_FOLDER = os.path.join("static", "avatars")
os.makedirs(AVATAR_FOLDER, exist_ok=True)

ALLOWED_AVATAR_EXT = {"jpg","jpeg","png","gif","webp"}

def ext_ok(fname):
    return "." in fname and fname.rsplit(".",1)[1].lower() in ALLOWED_AVATAR_EXT



# Função para verificar ficheiros permitidos
def ficheiro_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Função para obter conexão à base de dados
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # Para retornar como dicionário
    return db

# >>> ADD: tipos de reclamação permitidos por utilizador
def get_allowed_rec_tipos_for_current_user():
    # Admin vê tudo
    if is_admin():
        return None  # None => sem filtro
    if not can_reclamacoes():
        return []    # nenhum tipo
    db = get_db()
    rows = db.execute(
        "SELECT tipo FROM user_reclamacao_tipos WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()
    return [r["tipo"] for r in rows]
# <<< END ADD


# Fechar a conexão após cada request
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# Perfis sugeridos: 'admin_geral', 'admin', 'gestor', 'analista', 'leitor'
PERFIS = {
    "RELATORIOS_VIEW": {"admin_geral", "admin", "gestor", "analista", "leitor"},
    "USUARIOS_ADMIN": {"admin_geral", "admin"},
    "MENSAGENS_VIEW": {"admin_geral", "admin", "gestor", "analista"},
    "MENSAGENS_RESP": {"admin_geral", "admin"},
    "REGISTOS_VIEW":  {"admin_geral", "admin"},
}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def require_profiles(allowed: set[str]):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            perfil = session.get("perfil")
            if perfil not in allowed:
                return "Acesso negado", 403
            return view(*args, **kwargs)
        return wrapped
    return decorator

def log_acao(acao: str, tabela: str = ""):
    """Regista ações de administração/acesso."""
    try:
        db = get_db()
        user_id = session.get("user_id")
        db.execute(
            "INSERT INTO logs_acesso (user_id, acao, tabela, data) VALUES (?, ?, ?, datetime('now'))",
            (user_id, acao, tabela)
        )
        db.commit()
    except Exception:
        pass  # não quebra a app por falha de log

@app.route("/")
def index():
    return render_template("public/base.html")
from datetime import datetime, timedelta

# Função para adicionar dias úteis
def adicionar_dias_uteis(data_inicial, dias):
    data = data_inicial
    while dias > 0:
        data += timedelta(days=1)
        if data.weekday() < 5:  # Segunda (0) a sexta (4)
            dias -= 1
    return data



@app.context_processor
def inject_ano():
    return {'ano': datetime.now().year}

# >>> ADD: perms no contexto (menu/condicionais no template)
@app.context_processor
def inject_perms():
    return {
        "is_admin": is_admin(),
        "can_denuncias": can_denuncias(),
        "can_reclamacoes": can_reclamacoes(),
    }
# <<< END ADD
@app.context_processor
def inject_current_user():
    u = None
    try:
        if session.get("user_id"):
            u = get_db().execute(
                "SELECT id, nome, email, perfil, cargo, foto FROM usuarios WHERE id = ?",
                (session["user_id"],)
            ).fetchone()
    except Exception:
        u = None
    # Devolve um objeto (row) ou None. Usaremos 'current_user' no template.
    return {"current_user": u}


@app.context_processor
def inject_header_inboxes():
    """
    Disponibiliza no template:
      - notif_count: nº total de notificações recentes (denúncias + reclamações)
      - notif_items: lista (máx 5) com {origem, codigo, titulo, secund, data}
      - msg_count: nº de conversas com última mensagem do cidadão (entrante)
      - msg_items: lista (máx 5) com {origem, codigo, texto, delegacao, data}
    Regras:
      - Só inclui denúncias se can_denuncias()
      - Só inclui reclamações se can_reclamacoes() e tipo permitido
      - "Recentes": estado pendente OU submetidas nas últimas 24h
      - Mensagens: últimas por conversa em que o remetente foi 'cidadao'
    """
    try:
        if "user_id" not in session:
            return dict(notif_count=0, notif_items=[], msg_count=0, msg_items=[])

        db = get_db()

        # -------- NOTIFICAÇÕES (denúncias + reclamações) --------
        items = []

        # Denúncias (se o utilizador pode ver)
        if can_denuncias():
            rows = db.execute("""
                SELECT 
                  d.codigo_acomp AS codigo,
                  COALESCE(dg.nome, d.delegacao_id) AS delegacao,
                  d.data_submissao AS data
                FROM denuncias d
                LEFT JOIN delegacoes dg
                  ON dg.id = d.delegacao_id
                  OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(dg.nome)
                WHERE 
                  (d.estado IS NULL OR d.estado='pendente' 
                   OR datetime(d.data_submissao) >= datetime('now','-1 day'))
                ORDER BY d.data_submissao DESC
                LIMIT 10
            """).fetchall()
            for r in rows:
                items.append({
                    "origem": "denuncia",
                    "codigo": r["codigo"],
                    "titulo": "Nova denúncia",
                    "secund": r["delegacao"] or "—",
                    "data": r["data"],
                })

        # Reclamações (se o utilizador pode ver + filtro de tipos)
        if can_reclamacoes():
            tipos_allowed = get_allowed_rec_tipos_for_current_user()  # None=admin (sem filtro)
            base = """
                SELECT 
                  r.codigo_acomp AS codigo,
                  r.tipo,
                  COALESCE(dg.nome, r.delegacao_id) AS delegacao,
                  r.data_submissao AS data
                FROM reclamacoes r
                LEFT JOIN delegacoes dg
                  ON dg.id = r.delegacao_id
                  OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(dg.nome)
                WHERE 
                  (r.estado IS NULL OR r.estado='pendente'
                   OR datetime(r.data_submissao) >= datetime('now','-1 day'))
            """
            params = []
            if tipos_allowed is not None:
                if not tipos_allowed:
                    pass  # sem permissões → nada a fazer
                else:
                    placeholders = ",".join(["?"] * len(tipos_allowed))
                    base += f" AND r.tipo IN ({placeholders})"
                    params.extend(tipos_allowed)

            recs = db.execute(base + " ORDER BY r.data_submissao DESC LIMIT 10", params).fetchall()
            for r in recs:
                items.append({
                    "origem": "reclamacao",
                    "codigo": r["codigo"],
                    "titulo": "Nova reclamação",
                    "secund": r["delegacao"] or "—",
                    "data": r["data"],
                })

        # Ordena por data desc e limita a 5 para o dropdown
        items.sort(key=lambda x: x["data"], reverse=True)
        notif_items = items[:5]
        notif_count = len(items)

        # -------- MENSAGENS (última mensagem do cidadão em cada conversa) --------
        conv = db.execute("""
            WITH ult AS (
              SELECT m.*
              FROM mensagens m
              JOIN (
                SELECT codigo_acomp, MAX(id) AS max_id
                FROM mensagens
                GROUP BY codigo_acomp
              ) u ON u.max_id = m.id
            )
            SELECT 
              ult.codigo_acomp AS codigo,
              ult.conteudo     AS texto,
              ult.data_envio   AS data,
              CASE WHEN d.id IS NOT NULL THEN 'denuncia' ELSE 'reclamacao' END AS origem,
              COALESCE(dg.nome, COALESCE(dg2.nome, r.delegacao_id)) AS delegacao,
              r.tipo AS tipo_rec
            FROM ult
            LEFT JOIN denuncias d ON d.codigo_acomp = ult.codigo_acomp
            LEFT JOIN delegacoes dg
              ON dg.id = d.delegacao_id 
              OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(dg.nome)
            LEFT JOIN reclamacoes r ON r.codigo_acomp = ult.codigo_acomp
            LEFT JOIN delegacoes dg2
              ON dg2.id = r.delegacao_id 
              OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(dg2.nome)
            WHERE ult.remetente = 'cidadao'
            ORDER BY ult.data_envio DESC
        """).fetchall()

        msg_items = []
        for c in conv:
            # guards de permissão
            if c["origem"] == "denuncia" and not can_denuncias():
                continue
            if c["origem"] == "reclamacao":
                if not can_reclamacoes():
                    continue
                tipos_allowed = get_allowed_rec_tipos_for_current_user()
                if tipos_allowed is not None and c["tipo_rec"] not in tipos_allowed:
                    continue
            msg_items.append({
                "origem": c["origem"],
                "codigo": c["codigo"],
                "texto":  c["texto"],
                "delegacao": c["delegacao"] or "—",
                "data": c["data"],
            })

        msg_count = len(msg_items)
        msg_items = msg_items[:5]

        return dict(
            notif_count=notif_count,
            notif_items=notif_items,
            msg_count=msg_count,
            msg_items=msg_items
        )
    except Exception:
        return dict(notif_count=0, notif_items=[], msg_count=0, msg_items=[])


@app.route("/denuncia", methods=["GET", "POST"])
def denuncia():
    if request.method == "POST":
        db = get_db()
        dados = request.form
        tipo = dados.get("tipo_denuncia")
        delegacao = dados.get("delegacao")
        descricao = dados.get("descricao")
        data_ocorrencia = dados.get("data_ocorrencia")

        codigo = secrets.token_hex(5).upper()  # Ex: '6E1340FB80'
        hoje = date.today()
        prazo = adicionar_dias_uteis(hoje, 30)
 # Processar anexos
        anexos_paths = []
        if 'anexos' in request.files:
            for ficheiro in request.files.getlist('anexos'):
                if ficheiro and ficheiro_permitido(ficheiro.filename):
                    filename = secure_filename(ficheiro.filename)
                    caminho = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    ficheiro.save(caminho)
                    anexos_paths.append(filename)

        db.execute("""
            INSERT INTO denuncias (tipo, delegacao_id, descricao, anexos, data_ocorrencia, data_submissao, codigo_acomp, estado, prazo_resposta)
            VALUES (?, (SELECT id FROM delegacoes WHERE lower(nome)=?), ?, ?, ?, datetime('now'), ?, 'pendente', ?)

        """, (
            tipo, delegacao.lower(), descricao, json.dumps(anexos_paths),
            data_ocorrencia, codigo, prazo.isoformat()
        ))
        db.commit()

        session['codigo'] = codigo
        session['prazo'] = prazo.strftime('%d/%m/%Y')
        return redirect(url_for('denuncia_sucesso'))

    return render_template("public/denuncia.html", current_date=date.today().isoformat())

@app.route("/denuncia/sucesso")
def denuncia_sucesso():
    codigo = session.get("codigo")
    prazo = session.get("prazo")
    if not codigo or not prazo:
        return redirect(url_for('denuncia'))  # Redireciona se acedido indevidamente
    return render_template("public/denuncia_sucesso.html", codigo=codigo, prazo=prazo)



@app.route("/reclamacao", methods=["GET", "POST"])
def reclamacao():
    if request.method == "POST":
        db = get_db()
        dados = request.form

        codigo = secrets.token_hex(5).upper()
        prazo = adicionar_dias_uteis(datetime.today(), 15).date()

        anexos_paths = []
        if 'anexos' in request.files:
            for ficheiro in request.files.getlist('anexos'):
                if ficheiro and ficheiro_permitido(ficheiro.filename):
                    filename = secure_filename(ficheiro.filename)
                    caminho = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    ficheiro.save(caminho)
                    anexos_paths.append(filename)

        db.execute("""
            INSERT INTO reclamacoes (
                tipo, nome, contacto, descricao, anexos,
                data_ocorrencia, data_submissao, codigo_acomp,
                estado, delegacao_id, prazo_resposta
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, 'pendente', ?, ?)
        """, (
            dados.get("tipo_reclamacao"),
            dados.get("nome"),
            dados.get("contacto"),
            dados.get("descricao"),
            json.dumps(anexos_paths),
            dados.get("data_ocorrencia"),
            codigo,
            dados.get("delegacao"),
            prazo
        ))
        db.commit()

        session["codigo_acomp"] = codigo
        session["prazo_resposta"] = prazo.strftime("%d/%m/%Y")
        return redirect(url_for("reclamacao_sucesso"))

    return render_template("public/reclamacao.html", current_date=date.today().isoformat())

@app.route("/reclamacao/sucesso")
def reclamacao_sucesso():
    codigo = session.pop("codigo_acomp", None)
    prazo = session.pop("prazo_resposta", None)
    if not codigo or not prazo:
        return redirect(url_for("reclamacao"))
    return render_template("public/reclamacao_sucesso.html", codigo=codigo, prazo=prazo)



@app.route("/acompanhamento", methods=["GET", "POST"])
def acompanhamento():
    if request.method == "POST":
        codigo = request.form.get("codigo").strip().upper()
        return redirect(url_for("acompanhamento_detalhes", codigo=codigo))
    return render_template("public/acompanhamento.html")



@app.route("/acompanhamento/<codigo>")
def acompanhamento_detalhes(codigo):
    db = get_db()

    denuncia = db.execute("""
        SELECT d.*, dg.nome AS delegacao_nome
        FROM denuncias d
        LEFT JOIN delegacoes dg ON d.delegacao_id = dg.id OR lower(d.delegacao_id) = lower(dg.nome)
        WHERE d.codigo_acomp = ?
    """, (codigo,)).fetchone()

    reclamacao = None
    if not denuncia:
        reclamacao = db.execute("""
            SELECT r.*, dg.nome AS delegacao_nome
            FROM reclamacoes r
            LEFT JOIN delegacoes dg ON r.delegacao_id = dg.id OR lower(r.delegacao_id) = lower(dg.nome)
            WHERE r.codigo_acomp = ?
        """, (codigo,)).fetchone()

    if not denuncia and not reclamacao:
        return render_template("public/acompanhamento.html", tentativa=True, resultado=None)

    resultado = denuncia or reclamacao

    # Corrigido aqui:
    resultado = dict(denuncia or reclamacao)

    if resultado.get("anexos"):
        try:
            resultado["anexos"] = json.loads(resultado["anexos"])
        except Exception:
            resultado["anexos"] = []


    else:
        resultado = dict(resultado)

    mensagens = db.execute("""
        SELECT * FROM mensagens WHERE codigo_acomp = ? ORDER BY data_envio ASC
    """, (codigo,)).fetchall()

    return render_template("public/acompanhamento_detalhes.html", resultado=resultado, mensagens=mensagens)


@app.route("/responder", methods=["POST"])
def responder():
    db = get_db()
    codigo = request.form.get("codigo")
    conteudo = request.form.get("mensagem")

    if codigo and conteudo:
        tz = pytz.timezone("Africa/Maputo")
        agora = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        db.execute("""
            INSERT INTO mensagens (codigo_acomp, conteudo, remetente, data_envio)
            VALUES (?, ?, 'cidadao', ?)
        """, (codigo, conteudo, agora))
        db.commit()

    return redirect(url_for("acompanhamento_detalhes", codigo=codigo))



@app.route("/ajuda")
def ajuda():
    return render_template("public/ajuda.html")

    #Painel Adminstrativo

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None

    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        if not email or not senha:
            erro = "Preencha todos os campos."
        else:
            db = get_db()
            user = db.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()

            if user is None:
                erro = "Este email não está registado."
            elif not user["ativo"]:
                erro = "A sua conta está desactivada. Contacte o administrador."
            else:
                senha_hash = hashlib.sha256(senha.encode()).hexdigest()
                if senha_hash != user["senha"]:
                    erro = "Senha incorrecta."
                else:
                    # Login com sucesso
                    session["user_id"] = user["id"]
                    session["perfil"] = user["perfil"]
                    session["nome"] = user["nome"]
                    session["email"] = user["email"]
                    return redirect(url_for("painel"))

    return render_template("admin/login.html", erro=erro)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))






@app.route("/painel")
@login_required
def painel():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    # -------- filtros (GET) --------
    tz = pytz.timezone("Africa/Maputo")
    now = datetime.now(tz)

    try:
        ano = int(request.args.get("ano", now.year))
    except:
        ano = now.year

    mes = request.args.get("mes", f"{now.month:02d}")  # 'all' ou '01'..'12'
    visao_anual = (mes == "all")

    # rótulos de meses e dias
    meses_labels = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    dias_labels = []
    if not visao_anual:
        _, ndias = monthrange(ano, int(mes))
        dias_labels = [f"{d:02d}" for d in range(1, ndias+1)]

    # datas início/fim
    if visao_anual:
        data_ini = f"{ano}-01-01"
        data_fim = f"{ano}-12-31"
    else:
        data_ini = f"{ano}-{mes}-01"
        _, ndias = monthrange(ano, int(mes))
        data_fim = f"{ano}-{mes}-{ndias:02d}"

    periodo_label = f"{ano}" if visao_anual else f"{mes}/{ano}"

    # ---------- Permissões ----------
    see_den = can_denuncias()
    see_rec = can_reclamacoes()
    tipos_allowed = get_allowed_rec_tipos_for_current_user() if see_rec else None

    # where extra para reclamações (por tipo)
    rec_where = ""
    rec_params = []
    if see_rec and tipos_allowed is not None:
        if not tipos_allowed:
            # sem permissões => zera tudo já aqui
            rec_kpis = {"total":0,"pendentes":0,"em_analise":0,"concluidas":0,"arquivadas":0}
            rec_diaria = []
            rec_mensal = [0]*12
        else:
            placeholders = ",".join(["?"] * len(tipos_allowed))
            rec_where = f" AND reclamacoes.tipo IN ({placeholders})"
            rec_params = tipos_allowed

    # ---------- helpers ----------
    def kpis_periodo(tabela: str, extra_where: str = "", params=None):
        params = params or []
        sql = f"""
            SELECT 
              COUNT(*) AS total,
              SUM(CASE WHEN estado='pendente'   THEN 1 ELSE 0 END) AS pendentes,
              SUM(CASE WHEN estado='em_analise' THEN 1 ELSE 0 END) AS em_analise,
              SUM(CASE WHEN estado='concluida'  THEN 1 ELSE 0 END) AS concluidas,
              SUM(CASE WHEN estado='arquivada'  THEN 1 ELSE 0 END) AS arquivadas
            FROM {tabela}
            WHERE date(data_submissao) BETWEEN date(?) AND date(?) {extra_where}
        """
        row = db.execute(sql, [data_ini, data_fim] + params).fetchone()
        def _z(v): return int(v or 0)
        return {
            "total": _z(row["total"]),
            "pendentes": _z(row["pendentes"]),
            "em_analise": _z(row["em_analise"]),
            "concluidas": _z(row["concluidas"]),
            "arquivadas": _z(row["arquivadas"]),
        }

    def serie_diaria(tabela: str, extra_where: str = "", params=None):
        params = params or []
        if visao_anual:
            return []
        sql = f"""
            SELECT strftime('%d', data_submissao) AS dia, COUNT(*) AS qt
            FROM {tabela}
            WHERE date(data_submissao) BETWEEN date(?) AND date(?) {extra_where}
            GROUP BY strftime('%Y-%m-%d', data_submissao)
            ORDER BY 1
        """
        rows = db.execute(sql, [data_ini, data_fim] + params).fetchall()
        mapa = {r["dia"]: int(r["qt"]) for r in rows}
        return [mapa.get(d, 0) for d in dias_labels]

    def serie_mensal(tabela: str, extra_where: str = "", params=None):
        params = params or []
        if not visao_anual:
            return []
        sql = f"""
            SELECT strftime('%m', data_submissao) AS mm, COUNT(*) AS qt
            FROM {tabela}
            WHERE date(data_submissao) BETWEEN date(?) AND date(?) {extra_where}
            GROUP BY strftime('%Y-%m', data_submissao)
            ORDER BY 1
        """
        rows = db.execute(sql, [data_ini, data_fim] + params).fetchall()
        mapa = {r["mm"]: int(r["qt"]) for r in rows}
        return [mapa.get(f"{i:02d}", 0) for i in range(1,13)]

    def serie_semana(tabela: str, extra_where: str = "", params=None):
        """Contagem por dia da semana (1..6,0) -> Seg..Dom"""
        params = params or []
        sql = f"""
            SELECT strftime('%w', data_submissao) AS wd, COUNT(*) AS qt
            FROM {tabela}
            WHERE date(data_submissao) BETWEEN date(?) AND date(?) {extra_where}
            GROUP BY strftime('%Y-%m-%d', data_submissao), strftime('%w', data_submissao)
        """
        rows = db.execute(sql, [data_ini, data_fim] + params).fetchall()
        # sqlite: 0=Dom .. 6=Sáb; queremos ordem Seg(1)..Sáb(6),Dom(0)
        soma = {"0":0,"1":0,"2":0,"3":0,"4":0,"5":0,"6":0}
        for r in rows:
            k = r["wd"] or "0"
            soma[k] += int(r["qt"] or 0)
        ordem = ["1","2","3","4","5","6","0"]
        return [soma[o] for o in ordem]

    def top_delegacoes_rows(tabela: str, extra_where: str = "", params=None):
        params = params or []
        sql = f"""
          SELECT COALESCE(dg.nome, {tabela}.delegacao_id) AS delegacao, COUNT(*) AS qt
          FROM {tabela}
          LEFT JOIN delegacoes dg
            ON dg.id = {tabela}.delegacao_id
            OR LOWER(CAST({tabela}.delegacao_id AS TEXT)) = LOWER(dg.nome)
          WHERE date({tabela}.data_submissao) BETWEEN date(?) AND date(?) {extra_where}
          GROUP BY delegacao
          ORDER BY qt DESC
          LIMIT 10
        """
        return db.execute(sql, [data_ini, data_fim] + params).fetchall()

    def combinar_tops(den_rows, rec_rows):
        tot = {}
        for r in (den_rows or []):
            nm = r["delegacao"] or "—"
            tot[nm] = tot.get(nm, 0) + int(r["qt"] or 0)
        for r in (rec_rows or []):
            nm = r["delegacao"] or "—"
            tot[nm] = tot.get(nm, 0) + int(r["qt"] or 0)
        pares = sorted(tot.items(), key=lambda x: x[1], reverse=True)[:10]
        labels = [p[0] for p in pares]
        values = [p[1] for p in pares]
        return labels, values

    # ---------- DENÚNCIAS ----------
    den_kpis = den_diaria = den_mensal = den_semana = den_top_rows = None
    if see_den:
        den_kpis = kpis_periodo("denuncias")
        den_diaria = serie_diaria("denuncias")
        den_mensal = serie_mensal("denuncias")
        den_semana = serie_semana("denuncias")
        den_top_rows = top_delegacoes_rows("denuncias")

    # ---------- RECLAMAÇÕES ----------
    rec_kpis = rec_diaria = rec_mensal = rec_semana = rec_top_rows = None
    if see_rec:
        if tipos_allowed is not None and not tipos_allowed:
            rec_semana = [0,0,0,0,0,0,0]
        else:
            rec_kpis = kpis_periodo("reclamacoes", rec_where, rec_params)
            rec_diaria = serie_diaria("reclamacoes", rec_where, rec_params)
            rec_mensal = serie_mensal("reclamacoes", rec_where, rec_params)
            rec_semana = serie_semana("reclamacoes", rec_where, rec_params)
            rec_top_rows = top_delegacoes_rows("reclamacoes", rec_where, rec_params)

    # ---------- COMBINADO ----------
    combinado = None
    if see_den and see_rec and (den_kpis or rec_kpis):
        combinado = {
            "total": (den_kpis["total"] if den_kpis else 0) + (rec_kpis["total"] if rec_kpis else 0),
            "pendentes": (den_kpis["pendentes"] if den_kpis else 0) + (rec_kpis["pendentes"] if rec_kpis else 0),
            "em_analise": (den_kpis["em_analise"] if den_kpis else 0) + (rec_kpis["em_analise"] if rec_kpis else 0),
            "concluidas": (den_kpis["concluidas"] if den_kpis else 0) + (rec_kpis["concluidas"] if rec_kpis else 0),
            "arquivadas": (den_kpis["arquivadas"] if den_kpis else 0) + (rec_kpis["arquivadas"] if rec_kpis else 0),
        }

    # ---------- Distribuição por estado (donut) ----------
    estados_totais = [
        (den_kpis["pendentes"] if den_kpis else 0) + (rec_kpis["pendentes"] if rec_kpis else 0),
        (den_kpis["em_analise"] if den_kpis else 0) + (rec_kpis["em_analise"] if rec_kpis else 0),
        (den_kpis["concluidas"] if den_kpis else 0) + (rec_kpis["concluidas"] if rec_kpis else 0),
        (den_kpis["arquivadas"] if den_kpis else 0) + (rec_kpis["arquivadas"] if rec_kpis else 0),
    ]

    # ---------- Semana & Top Delegações (para os novos gráficos) ----------
    semana_labels = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
    den_sem = den_semana or [0]*7
    rec_sem = rec_semana or [0]*7
    semana_total = [ (den_sem[i] if see_den else 0) + (rec_sem[i] if see_rec else 0) for i in range(7) ]

    top_labels, top_values = combinar_tops(den_top_rows, rec_top_rows)

    # Cabeçalho (se ainda não tens, deixa vazio)
    notif_items = []
    msg_items = []
    notif_count = 0
    msg_count = 0

    return render_template(
        "admin/dashboard.html",
        # filtros/labels
        ano=ano, mes=mes, visao_anual=visao_anual, periodo_label=periodo_label,
        meses_labels=meses_labels, dias_labels=dias_labels,

        # kpis + séries
        den_kpis=den_kpis, den_diaria=den_diaria or [], den_mensal=den_mensal or [],
        rec_kpis=rec_kpis, rec_diaria=rec_diaria or [], rec_mensal=rec_mensal or [],
        combinado=combinado,
        estados_totais=estados_totais,

        # novos gráficos
        semana_labels=semana_labels, semana_total=semana_total,
        top_labels=top_labels, top_values=top_values,

        # permissões
        see_den=see_den, see_rec=see_rec,

        # header
        notif_items=notif_items, msg_items=msg_items,
        notif_count=notif_count, msg_count=msg_count
    )

@app.route("/admin/denuncias")
@require_roles(ROLES_DEN)
def ver_denuncias():
    db = get_db()

    # --- parâmetros de filtro (novos + antigos) ---
    tipo         = request.args.get("tipo") or None
    estado       = request.args.get("estado") or None
    mes          = request.args.get("mes") or None          # YYYY-MM
    data_inicio  = request.args.get("data_inicio") or None  # YYYY-MM-DD
    data_fim     = request.args.get("data_fim") or None     # YYYY-MM-DD

    # --- WHERE comum (sem "estado") para usar nos KPIs ---
    where_parts_no_estado = ["1=1"]
    params_no_estado = []

    # Mês (só se NÃO houver intervalo De/Até)
    if mes and not (data_inicio or data_fim):
        try:
            from datetime import datetime, timedelta
            dt_ini = datetime.strptime(mes + "-01", "%Y-%m-%d").date()
            # último dia do mês
            if dt_ini.month == 12:
                dt_fim = dt_ini.replace(year=dt_ini.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                dt_fim = dt_ini.replace(month=dt_ini.month + 1, day=1) - timedelta(days=1)
            where_parts_no_estado.append("date(data_submissao) BETWEEN date(?) AND date(?)")
            params_no_estado.extend([dt_ini.isoformat(), dt_fim.isoformat()])
        except ValueError:
            pass

    # Intervalo De/Até (sempre por data_submissao)
    if data_inicio:
        where_parts_no_estado.append("date(data_submissao) >= date(?)")
        params_no_estado.append(data_inicio)
    if data_fim:
        where_parts_no_estado.append("date(data_submissao) <= date(?)")
        params_no_estado.append(data_fim)

    # Tipo
    if tipo:
        where_parts_no_estado.append("tipo = ?")
        params_no_estado.append(tipo)

    # Constrói WHERE base (sem estado)
    where_no_estado = " AND ".join(where_parts_no_estado)

    # --- WHERE com "estado" (para a listagem) ---
    where_parts = where_parts_no_estado[:]
    params = params_no_estado[:]

    if estado:
        if estado == "pendente":
            # trata pendente como pendente/NULL/vazio
            where_parts.append("(estado = 'pendente' OR estado IS NULL OR estado = '')")
        else:
            where_parts.append("estado = ?")
            params.append(estado)

    where = " AND ".join(where_parts)

    # --- LISTA (respeita todos os filtros, inclusive estado) ---
    sql_lista = f"SELECT * FROM denuncias WHERE {where} ORDER BY data_submissao DESC"
    denuncias = db.execute(sql_lista, params).fetchall()

    # --- KPIs (no conjunto filtrado, porém SEM filtrar por 'estado') ---
    sql_kpis = f"""
        SELECT 
          COUNT(*) AS total,
          SUM(CASE WHEN COALESCE(NULLIF(estado,''),'pendente')='pendente' THEN 1 ELSE 0 END) AS pendentes,
          SUM(CASE WHEN estado='em_analise' THEN 1 ELSE 0 END) AS em_analise,
          SUM(CASE WHEN estado='concluida'  THEN 1 ELSE 0 END) AS concluidas,
          SUM(CASE WHEN estado='arquivada'  THEN 1 ELSE 0 END) AS arquivadas
        FROM denuncias
        WHERE {where_no_estado}
    """
    k = db.execute(sql_kpis, params_no_estado).fetchone()
    def _z(v): return int(v or 0)

    total        = _z(k["total"])
    pendentes    = _z(k["pendentes"])
    em_analise   = _z(k["em_analise"])
    concluidas   = _z(k["concluidas"])
    arquivadas   = _z(k["arquivadas"])

    return render_template(
        "admin/ver_denuncias.html",
        denuncias=denuncias,

        # KPIs (já filtrados)
        total_denuncias=total,
        pendentes=pendentes,
        em_analise=em_analise,
        concluidas=concluidas,
        arquivadas=arquivadas,

        # devolve filtros para o template manter seleção
        tipo=tipo, estado=estado, mes=mes,
        data_inicio=data_inicio, data_fim=data_fim
    )




@app.route("/admin/denuncias/<int:id>", methods=["GET","POST"])
@require_roles(ROLES_DEN)
def ver_detalhes_denuncia(id):
    db = get_db()
    denuncia = db.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
    if not denuncia:
        return "Denúncia não encontrada", 404

    # Atualiza estado se submetido
    if request.method == "POST" and request.form.get("novo_estado"):
        novo_estado = request.form["novo_estado"]
        db.execute("UPDATE denuncias SET estado = ? WHERE id = ?", (novo_estado, id))
        db.commit()
        denuncia = db.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()

    # Anexos
    anexos = json.loads(denuncia["anexos"]) if denuncia["anexos"] else []

    # Última do RH e última do colaborador
    mensagens = db.execute("""
        SELECT * FROM mensagens 
        WHERE codigo_acomp = ? 
        ORDER BY data_envio ASC
    """, (denuncia["codigo_acomp"],)).fetchall()

    ultima_admin = next((m for m in reversed(mensagens) if m["remetente"] == "admin"), None)
    ultima_cidadao = next((m for m in reversed(mensagens) if m["remetente"] == "cidadao"), None)

    return render_template("admin/ver_detalhes_denuncia.html",
                           denuncia=denuncia,
                           anexos=anexos,
                           ultima_admin=ultima_admin,
                           ultima_cidadao=ultima_cidadao)



@app.route("/admin/denuncias/responder", methods=["POST"])
@require_roles(ROLES_DEN)
def responder_denuncia_ajax():
    db = get_db()
    codigo = request.form.get("codigo")
    mensagem = request.form.get("mensagem")

    if not codigo or not mensagem:
        return jsonify({"erro": "Dados incompletos"}), 400

    # Hora local de Maputo
    hora_local = datetime.now(pytz.timezone("Africa/Maputo")).strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        INSERT INTO mensagens (codigo_acomp, conteudo, remetente, data_envio)
        VALUES (?, ?, 'admin', ?)
    """, (codigo, mensagem, hora_local))
    db.commit()

    return jsonify({"remetente": "Admin", "conteudo": mensagem, "data_envio": "agora mesmo"})


@app.route("/admin/reclamacoes")
@require_roles(ROLES_REC)
def ver_reclamacoes():
    db = get_db()
    tipo = request.args.get("tipo")
    estado = request.args.get("estado")
    data = request.args.get("data")

    query = "SELECT * FROM reclamacoes WHERE 1=1"
    params = []

    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)

    if estado:
        query += " AND estado = ?"
        params.append(estado)

    if data:
        query += " AND date(data_submissao) = ?"
        params.append(data)
# >>> AQUI entra o filtro por tipos permitidos
    tipos_allowed = get_allowed_rec_tipos_for_current_user()
    if tipos_allowed is not None:  # None = admin, vê tudo
        if not tipos_allowed:
            # não tem nenhum tipo permitido → devolve vazio
            return render_template("admin/ver_reclamacoes.html",
                                   reclamacoes=[],
                                   total_reclamacoes=0,
                                   pendentes=0,
                                   em_analise=0,
                                   concluidas=0,
                                   arquivadas=0,
                                   tipo=tipo,
                                   estado=estado,
                                   data=data)
        placeholders = ",".join(["?"] * len(tipos_allowed))
        query += f" AND tipo IN ({placeholders})"
        params.extend(tipos_allowed)
    # <<< END ADD       
    reclamacoes = db.execute(query + " ORDER BY data_submissao DESC", params).fetchall()

    total = db.execute("SELECT COUNT(*) FROM reclamacoes").fetchone()[0]
    pendentes = db.execute("SELECT COUNT(*) FROM reclamacoes WHERE estado = 'pendente'").fetchone()[0]
    em_analise = db.execute("SELECT COUNT(*) FROM reclamacoes WHERE estado = 'em_analise'").fetchone()[0]
    concluidas = db.execute("SELECT COUNT(*) FROM reclamacoes WHERE estado = 'concluida'").fetchone()[0]
    arquivadas = db.execute("SELECT COUNT(*) FROM reclamacoes WHERE estado = 'arquivada'").fetchone()[0]

    return render_template("admin/ver_reclamacoes.html",
                           reclamacoes=reclamacoes,
                           total_reclamacoes=total,
                           pendentes=pendentes,
                           em_analise=em_analise,
                           concluidas=concluidas,
                           arquivadas=arquivadas,
                           tipo=tipo,
                           estado=estado,
                           data=data)


@app.route("/admin/reclamacoes/<int:id>", methods=["GET","POST"])
@require_roles(ROLES_REC)
def ver_detalhes_reclamacao(id):
    db = get_db()
    reclamacao = db.execute("SELECT * FROM reclamacoes WHERE id = ?", (id,)).fetchone()
       # >>> ADD: guarda de tipo
    tipos_allowed = get_allowed_rec_tipos_for_current_user()
    if tipos_allowed is not None and reclamacao and reclamacao["tipo"] not in tipos_allowed:
        from flask import abort
        return abort(403)
# <<< END ADD

    if not reclamacao:
        return "Reclamação não encontrada", 404

    if request.method == "POST" and request.form.get("novo_estado"):
        novo_estado = request.form["novo_estado"]
        db.execute("UPDATE reclamacoes SET estado = ? WHERE id = ?", (novo_estado, id))
        db.commit()
        reclamacao = db.execute("SELECT * FROM reclamacoes WHERE id = ?", (id,)).fetchone()

    anexos = json.loads(reclamacao["anexos"]) if reclamacao["anexos"] else []

    mensagens = db.execute("""
        SELECT * FROM mensagens 
        WHERE codigo_acomp = ? 
        ORDER BY data_envio ASC
    """, (reclamacao["codigo_acomp"],)).fetchall()

    ultima_admin = next((m for m in reversed(mensagens) if m["remetente"] == "admin"), None)
    ultima_cidadao = next((m for m in reversed(mensagens) if m["remetente"] == "cidadao"), None)

    return render_template("admin/ver_detalhes_reclamacao.html",
                           reclamacao=reclamacao,
                           anexos=anexos,
                           ultima_admin=ultima_admin,
                           ultima_cidadao=ultima_cidadao)

@app.route("/admin/reclamacoes/responder", methods=["POST"])
@require_roles(ROLES_REC)
def responder_reclamacao_ajax():
    db = get_db()
    codigo = request.form.get("codigo")
    mensagem = request.form.get("mensagem")

    if not codigo or not mensagem:
        return jsonify({"erro": "Dados incompletos"}), 400

    # Hora local de Maputo
    hora_local = datetime.now(pytz.timezone("Africa/Maputo")).strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        INSERT INTO mensagens (codigo_acomp, conteudo, remetente, data_envio)
        VALUES (?, ?, 'admin', ?)
    """, (codigo, mensagem, hora_local))
    db.commit()

    return jsonify({"remetente": "Admin", "conteudo": mensagem, "data_envio": "agora mesmo"})

@app.route("/admin/reclamacoes/alterar_estado", methods=["POST"])
def alterar_estado_reclamacao():
    db = get_db()
    data = request.get_json(silent=True) or {}
    rec_id = data.get("id")
    novo_estado = data.get("novo_estado")
    if not rec_id or not novo_estado:
        return jsonify({"erro": "Dados incompletos"}), 400

    db.execute("UPDATE reclamacoes SET estado = ? WHERE id = ?", (novo_estado, rec_id))
    db.commit()
    return jsonify({"ok": True})




@app.route("/admin/mensagens")
def ver_mensagens():
    db = get_db()

    # Pega a última mensagem de cada conversa (uma linha por código)
    # >>> MODIFY: incluir tipos e origem no resultado
    conversas = db.execute("""
     WITH ult AS (
      SELECT m.*
      FROM mensagens m
      JOIN (
        SELECT codigo_acomp, MAX(id) AS max_id
        FROM mensagens
        GROUP BY codigo_acomp
      ) u ON u.max_id = m.id
    )
    SELECT 
      ult.codigo_acomp,
      ult.conteudo       AS ultima_mensagem,
      ult.data_envio     AS data_ultima,
      d.id               AS denuncia_id,
      r.id               AS reclamacao_id,
      d.tipo             AS tipo_denuncia,
      r.tipo             AS tipo_reclamacao
    FROM ult
    LEFT JOIN denuncias   d ON d.codigo_acomp   = ult.codigo_acomp
    LEFT JOIN reclamacoes r ON r.codigo_acomp   = ult.codigo_acomp
    ORDER BY ult.data_envio DESC
""").fetchall()
# <<< END MODIFY
# >>> ADD: filtro por permissões
    tipos_allowed = get_allowed_rec_tipos_for_current_user()
    filtradas = []
    for c in conversas:
     if can_denuncias() and c["denuncia_id"]:
        filtradas.append(c)
        continue
     if can_reclamacoes() and c["reclamacao_id"]:
        if tipos_allowed is None or c["tipo_reclamacao"] in tipos_allowed:
            filtradas.append(c)
    conversas = filtradas
# <<< END ADD

    # Conversa ativa (querystring ?codigo=... ou primeira)
    codigo_param = request.args.get("codigo")
    codigos = [c["codigo_acomp"] for c in conversas]
    if codigo_param and codigo_param in codigos:
        codigo_ativo = codigo_param
    else:
        codigo_ativo = codigos[0] if codigos else None

    # Mensagens da conversa ativa
    mensagens = []
    if codigo_ativo:
        mensagens = db.execute("""
            SELECT remetente, conteudo, data_envio
            FROM mensagens 
            WHERE codigo_acomp = ?
            ORDER BY data_envio ASC
        """, (codigo_ativo,)).fetchall()

    return render_template(
        "admin/ver_mensagens.html",
        conversas=conversas,
        mensagens=mensagens,
        codigo_ativo=codigo_ativo
    )


@app.route("/admin/mensagens/<codigo_acomp>")
def ver_conversa(codigo_acomp):
    db = get_db()
    # >>> ADD: guard da conversa por tipo/origem
    d = db.execute("SELECT id FROM denuncias WHERE codigo_acomp=?", (codigo_acomp,)).fetchone()
    r = db.execute("SELECT id, tipo FROM reclamacoes WHERE codigo_acomp=?", (codigo_acomp,)).fetchone()

    from flask import abort
    if d and not can_denuncias():
      return abort(403)
    if r and not can_reclamacoes():
      return abort(403)
    if r:
      tipos_allowed = get_allowed_rec_tipos_for_current_user()
      if tipos_allowed is not None and r["tipo"] not in tipos_allowed:
        return abort(403)
# <<< END ADD

    msgs = db.execute("""
        SELECT remetente, conteudo, data_envio
        FROM mensagens 
        WHERE codigo_acomp = ?
        ORDER BY data_envio ASC
    """, (codigo_acomp,)).fetchall()

    return jsonify([
        {
            "remetente": m["remetente"],
            "conteudo":  m["conteudo"],
            "data_envio": m["data_envio"]
        } for m in msgs
    ])


@app.route("/admin/mensagens/responder", methods=["POST"])
@require_roles(ROLES_DEN | ROLES_REC)
def responder_mensagem_ajax():
    db = get_db()

    # pega do form
    codigo = request.form.get("codigo")
    mensagem = request.form.get("mensagem")

    if not codigo or not mensagem:
        return jsonify({"erro": "Dados incompletos"}), 400

    # --- guard de permissões por origem/tipo ---
    d = db.execute("SELECT id FROM denuncias WHERE codigo_acomp = ?", (codigo,)).fetchone()
    r = db.execute("SELECT id, tipo FROM reclamacoes WHERE codigo_acomp = ?", (codigo,)).fetchone()

    from flask import abort
    if d and not can_denuncias():
        return abort(403)
    if r and not can_reclamacoes():
        return abort(403)
    if r:
        tipos_allowed = get_allowed_rec_tipos_for_current_user()
        if tipos_allowed is not None and r["tipo"] not in tipos_allowed:
            return abort(403)
    # --- fim guard ---

    hora_local = datetime.now(pytz.timezone("Africa/Maputo")).strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        INSERT INTO mensagens (codigo_acomp, conteudo, remetente, data_envio)
        VALUES (?, ?, 'admin', ?)
    """, (codigo, mensagem, hora_local))
    db.commit()

    return jsonify({
        "ok": True,
        "remetente": "admin",
        "conteudo": mensagem,
        "data_envio": hora_local,
        "codigo": codigo
    })


@app.route("/admin/relatorios/denuncias")
@require_roles(ROLES_DEN)
def relatorio_denuncias():
    log_acao("ver", "relatorio_denuncias")
    db = get_db()

    # === Parâmetros de filtro (sem "periodo_base") ===
    data_inicio = request.args.get("data_inicio")
    data_fim    = request.args.get("data_fim")
    mes         = request.args.get("mes")          # formato YYYY-MM
    tipo        = request.args.get("tipo")
    estado      = request.args.get("estado")
    delegacao   = request.args.get("delegacao")

    query = """
        SELECT 
            d.id,
            d.codigo_acomp,
            d.tipo,
            d.data_submissao,
            d.data_ocorrencia,
            d.estado,
            COALESCE(dg.nome, d.delegacao_id) AS delegacao
        FROM denuncias d
        LEFT JOIN delegacoes dg
               ON d.delegacao_id = dg.id
               OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(dg.nome)
        WHERE 1=1
    """
    params = []

    # === Filtro por mês (YYYY-MM) ===
    # Se vier "mes" e NÃO vierem datas específicas, aplica o mês inteiro
    if mes and not (data_inicio or data_fim):
        try:
            # Primeiro dia do mês
            dt_ini = datetime.strptime(mes + "-01", "%Y-%m-%d").date()
            # Calcular último dia do mês
            if dt_ini.month == 12:
                dt_fim = dt_ini.replace(year=dt_ini.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                dt_fim = dt_ini.replace(month=dt_ini.month + 1, day=1) - timedelta(days=1)

            query += " AND date(d.data_submissao) BETWEEN date(?) AND date(?)"
            params.extend([dt_ini.isoformat(), dt_fim.isoformat()])
        except ValueError:
            pass

    # === Filtro por intervalo de datas (sempre pela data_submissao) ===
    if data_inicio:
        try:
            datetime.strptime(data_inicio, "%Y-%m-%d")
            query += " AND date(d.data_submissao) >= date(?)"
            params.append(data_inicio)
        except ValueError:
            pass

    if data_fim:
        try:
            datetime.strptime(data_fim, "%Y-%m-%d")
            query += " AND date(d.data_submissao) <= date(?)"
            params.append(data_fim)
        except ValueError:
            pass

    # === Tipo de denúncia ===
    if tipo:
        query += " AND d.tipo = ?"
        params.append(tipo)

    # === Estado ===
    if estado:
        query += " AND d.estado = ?"
        params.append(estado)

    # === Delegação (via select) ===
    if delegacao:
        # procura no nome da delegacao (dg.nome) e também no que estiver em delegacao_id
        query += " AND (LOWER(COALESCE(dg.nome, '')) = LOWER(?) OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(?))"
        params.extend([delegacao, delegacao])

    query += " ORDER BY d.data_submissao DESC"

    denuncias = db.execute(query, params).fetchall()

    return render_template("admin/relatorio_denuncias.html", denuncias=denuncias)

@app.route("/admin/relatorios/denuncias/pdf")
@require_roles(ROLES_DEN)
def relatorio_denuncias_pdf():
    db = get_db()

    # === Parâmetros (iguais à listagem) ===
    data_inicio = request.args.get("data_inicio")
    data_fim    = request.args.get("data_fim")
    mes         = request.args.get("mes")
    tipo        = request.args.get("tipo")
    estado      = request.args.get("estado")
    delegacao   = request.args.get("delegacao")

    query = """
        SELECT 
            d.id,
            d.codigo_acomp,
            d.tipo,
            d.data_submissao,
            d.data_ocorrencia,
            d.estado,
            COALESCE(dg.nome, d.delegacao_id) AS delegacao
        FROM denuncias d
        LEFT JOIN delegacoes dg
               ON d.delegacao_id = dg.id
               OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(dg.nome)
        WHERE 1=1
    """
    params = []

    # === Mês (YYYY-MM) ===
    if mes and not (data_inicio or data_fim):
        try:
            dt_ini = datetime.strptime(mes + "-01", "%Y-%m-%d").date()
            if dt_ini.month == 12:
                dt_fim = dt_ini.replace(year=dt_ini.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                dt_fim = dt_ini.replace(month=dt_ini.month + 1, day=1) - timedelta(days=1)
            query += " AND date(d.data_submissao) BETWEEN date(?) AND date(?)"
            params.extend([dt_ini.isoformat(), dt_fim.isoformat()])
        except ValueError:
            pass

    # === Datas específicas (submissão) ===
    if data_inicio:
        try:
            datetime.strptime(data_inicio, "%Y-%m-%d")
            query += " AND date(d.data_submissao) >= date(?)"
            params.append(data_inicio)
        except ValueError:
            pass

    if data_fim:
        try:
            datetime.strptime(data_fim, "%Y-%m-%d")
            query += " AND date(d.data_submissao) <= date(?)"
            params.append(data_fim)
        except ValueError:
            pass

    # === Tipo / Estado ===
    if tipo:
        query += " AND d.tipo = ?"
        params.append(tipo)
    if estado:
        query += " AND d.estado = ?"
        params.append(estado)

    # === Delegação ===
    if delegacao:
        query += " AND (LOWER(COALESCE(dg.nome, '')) = LOWER(?) OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(?))"
        params.extend([delegacao, delegacao])

    query += " ORDER BY d.data_submissao DESC"
    denuncias = db.execute(query, params).fetchall()

    # === KPIs (totais por estado) no conjunto filtrado ===
    total        = len(denuncias)
    pendentes    = sum(1 for r in denuncias if (r["estado"] or "pendente") == "pendente")
    em_analise   = sum(1 for r in denuncias if r["estado"] == "em_analise")
    concluidas   = sum(1 for r in denuncias if r["estado"] == "concluida")
    arquivadas   = sum(1 for r in denuncias if r["estado"] == "arquivada")

    kpis = {
        "total": total,
        "pendentes": pendentes,
        "em_analise": em_analise,
        "concluidas": concluidas,
        "arquivadas": arquivadas
    }

    # === Metadados e filtros exibidos no PDF ===
    gerado_em = datetime.now(pytz.timezone("Africa/Maputo")).strftime("%d/%m/%Y %H:%M")
    filtros = {
        "mes": mes,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipo": tipo,
        "estado": estado,
        "delegacao": delegacao
    }

    # === LOGO via caminho local (file://) ===
    # Ajusta o caminho conforme a tua estrutura (ex.: static/img/logo.png)
    logo_file = Path(app.static_folder) / "img" / "logo.png"
    logo_src = logo_file.as_uri() if logo_file.exists() else None
    # Ex.: file:///C:/.../static/img/logo.png

    # === HTML do PDF ===
    html_str = render_template(
        "admin/relatorio_denuncias_pdf.html",
        denuncias=denuncias,
        gerado_em=gerado_em,
        filtros=filtros,
        kpis=kpis,
        logo_src=logo_src
    )

    # === Config wkhtmltopdf ===
    config = pdfkit.configuration(
        wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"  # ajuste se necessário
    )

    options = {
        "page-size": "A4",
        "orientation": "Landscape",
        "margin-top": "12mm",
        "margin-right": "10mm",
        "margin-bottom": "12mm",
        "margin-left": "10mm",
        "encoding": "UTF-8",
        "enable-local-file-access": "",                # permite file://
        "footer-center": "Página [page] de [toPage]",  # paginação no rodapé
        "footer-font-size": "9",
        "quiet": "",
    }

    pdf_bytes = pdfkit.from_string(html_str, False, options=options, configuration=config)
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="relatorio_denuncias.pdf"'})

@app.route("/admin/relatorios/reclamacoes")
@require_roles(ROLES_REC)
def relatorio_reclamacoes():
    log_acao("ver", "relatorio_reclamacoes")
    db = get_db()

    data_inicio = request.args.get("data_inicio")
    data_fim    = request.args.get("data_fim")
    mes         = request.args.get("mes")
    tipo        = request.args.get("tipo")
    estado      = request.args.get("estado")
    delegacao   = request.args.get("delegacao")

    query = """
        SELECT
            r.id,
            r.codigo_acomp,
            r.tipo,
            r.data_submissao,
            r.data_ocorrencia,
            r.estado,
            COALESCE(dg.nome, r.delegacao_id) AS delegacao
        FROM reclamacoes r
        LEFT JOIN delegacoes dg
               ON r.delegacao_id = dg.id
               OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(dg.nome)
        WHERE 1=1
    """
    params = []

    # Mês (YYYY-MM)
    if mes and not (data_inicio or data_fim):
        try:
            dt_ini = datetime.strptime(mes + "-01", "%Y-%m-%d").date()
            if dt_ini.month == 12:
                dt_fim = dt_ini.replace(year=dt_ini.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                dt_fim = dt_ini.replace(month=dt_ini.month + 1, day=1) - timedelta(days=1)
            query += " AND date(r.data_submissao) BETWEEN date(?) AND date(?)"
            params.extend([dt_ini.isoformat(), dt_fim.isoformat()])
        except ValueError:
            pass

    # Intervalo de datas (sempre por data_submissao)
    if data_inicio:
        try:
            datetime.strptime(data_inicio, "%Y-%m-%d")
            query += " AND date(r.data_submissao) >= date(?)"
            params.append(data_inicio)
        except ValueError:
            pass

    if data_fim:
        try:
            datetime.strptime(data_fim, "%Y-%m-%d")
            query += " AND date(r.data_submissao) <= date(?)"
            params.append(data_fim)
        except ValueError:
            pass

    # Tipo / Estado / Delegação
    if tipo:
        query += " AND r.tipo = ?"
        params.append(tipo)

    if estado:
        query += " AND r.estado = ?"
        params.append(estado)

    if delegacao:
        query += " AND (LOWER(COALESCE(dg.nome, '')) = LOWER(?) OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(?))"
        params.extend([delegacao, delegacao])
# >>> ADD: restringir pelos tipos permitidos ao utilizador atual
    tipos_allowed = get_allowed_rec_tipos_for_current_user()  # None = admin (sem restrição)
    if tipos_allowed is not None:
        if not tipos_allowed:
            # sem permissões → lista vazia
            return render_template("admin/relatorio_reclamacoes.html", reclamacoes=[])
        placeholders = ",".join(["?"] * len(tipos_allowed))
        query += f" AND r.tipo IN ({placeholders})"
        params.extend(tipos_allowed)
    # <<< END ADD 
    query += " ORDER BY r.data_submissao DESC"

    reclamacoes = db.execute(query, params).fetchall()

    return render_template("admin/relatorio_reclamacoes.html", reclamacoes=reclamacoes)

# --- PDF: Relatório de Reclamações ---
@app.route("/admin/relatorios/reclamacoes/pdf")
@require_roles(ROLES_REC)
def relatorio_reclamacoes_pdf():
    db = get_db()

    # === Parâmetros (iguais à listagem) ===
    data_inicio = request.args.get("data_inicio")
    data_fim    = request.args.get("data_fim")
    mes         = request.args.get("mes")          # formato YYYY-MM
    tipo        = request.args.get("tipo")
    estado      = request.args.get("estado")
    delegacao   = request.args.get("delegacao")

    query = """
        SELECT 
            r.id,
            r.codigo_acomp,
            r.tipo,
            r.data_submissao,
            r.data_ocorrencia,
            r.estado,
            COALESCE(dg.nome, r.delegacao_id) AS delegacao
        FROM reclamacoes r
        LEFT JOIN delegacoes dg
               ON r.delegacao_id = dg.id
               OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(dg.nome)
        WHERE 1=1
    """
    params = []

    # === Mês (YYYY-MM) ===
    if mes and not (data_inicio or data_fim):
        try:
            dt_ini = datetime.strptime(mes + "-01", "%Y-%m-%d").date()
            if dt_ini.month == 12:
                dt_fim = dt_ini.replace(year=dt_ini.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                dt_fim = dt_ini.replace(month=dt_ini.month + 1, day=1) - timedelta(days=1)
            query += " AND date(r.data_submissao) BETWEEN date(?) AND date(?)"
            params.extend([dt_ini.isoformat(), dt_fim.isoformat()])
        except ValueError:
            pass

    # === Datas específicas (sempre pela data_submissao) ===
    if data_inicio:
        try:
            datetime.strptime(data_inicio, "%Y-%m-%d")
            query += " AND date(r.data_submissao) >= date(?)"
            params.append(data_inicio)
        except ValueError:
            pass

    if data_fim:
        try:
            datetime.strptime(data_fim, "%Y-%m-%d")
            query += " AND date(r.data_submissao) <= date(?)"
            params.append(data_fim)
        except ValueError:
            pass

    # === Tipo / Estado ===
    if tipo:
        query += " AND r.tipo = ?"
        params.append(tipo)
    if estado:
        query += " AND r.estado = ?"
        params.append(estado)

    # === Delegação (select) ===
    if delegacao:
        query += " AND (LOWER(COALESCE(dg.nome, '')) = LOWER(?) OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(?))"
        params.extend([delegacao, delegacao])
     # >>> ADD: restringir pelos tipos permitidos ao utilizador atual (mesma lógica)
    tipos_allowed = get_allowed_rec_tipos_for_current_user()
    if tipos_allowed is not None:
        if not tipos_allowed:
            # sem permissões → PDF vazio com KPIs a zero
            reclamacoes = []
            kpis = {"total":0,"pendentes":0,"em_analise":0,"concluidas":0,"arquivadas":0}
            gerado_em = datetime.now(pytz.timezone("Africa/Maputo")).strftime("%d/%m/%Y %H:%M")
            filtros = {"mes":mes,"data_inicio":data_inicio,"data_fim":data_fim,"tipo":tipo,"estado":estado,"delegacao":delegacao}
            logo_file = Path(app.static_folder) / "img" / "logo.png"
            logo_src = logo_file.as_uri() if logo_file.exists() else None
            html_str = render_template("admin/relatorio_reclamacoes_pdf.html",
                                       reclamacoes=reclamacoes, gerado_em=gerado_em,
                                       filtros=filtros, kpis=kpis, logo_src=logo_src)
            config = pdfkit.configuration(wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe")
            options = {"page-size":"A4","orientation":"Landscape","margin-top":"12mm","margin-right":"10mm",
                       "margin-bottom":"12mm","margin-left":"10mm","encoding":"UTF-8",
                       "enable-local-file-access":"","footer-center":"Página [page] de [toPage]","footer-font-size":"9","quiet":""}
            pdf_bytes = pdfkit.from_string(html_str, False, options=options, configuration=config)
            return Response(pdf_bytes, mimetype="application/pdf",
                            headers={"Content-Disposition": 'inline; filename="relatorio_reclamacoes.pdf"'})
        placeholders = ",".join(["?"] * len(tipos_allowed))
        query += f" AND r.tipo IN ({placeholders})"
        params.extend(tipos_allowed)
    # <<< END ADD
    query += " ORDER BY r.data_submissao DESC"
    reclamacoes = db.execute(query, params).fetchall()

    # === KPIs (totais por estado) ===
    total        = len(reclamacoes)
    pendentes    = sum(1 for r in reclamacoes if (r["estado"] or "pendente") == "pendente")
    em_analise   = sum(1 for r in reclamacoes if r["estado"] == "em_analise")
    concluidas   = sum(1 for r in reclamacoes if r["estado"] == "concluida")
    arquivadas   = sum(1 for r in reclamacoes if r["estado"] == "arquivada")

    kpis = {
        "total": total,
        "pendentes": pendentes,
        "em_analise": em_analise,
        "concluidas": concluidas,
        "arquivadas": arquivadas
    }

    # === Metadados / filtros exibidos no PDF ===
    gerado_em = datetime.now(pytz.timezone("Africa/Maputo")).strftime("%d/%m/%Y %H:%M")
    filtros = {
        "mes": mes,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipo": tipo,
        "estado": estado,
        "delegacao": delegacao
    }

    # === LOGO local (file://) ===
    
    logo_file = Path(app.static_folder) / "img" / "logo.png"
    logo_src = logo_file.as_uri() if logo_file.exists() else None

    # === Render do HTML ===
    html_str = render_template(
        "admin/relatorio_reclamacoes_pdf.html",
        reclamacoes=reclamacoes,
        gerado_em=gerado_em,
        filtros=filtros,
        kpis=kpis,
        logo_src=logo_src
    )

    # === pdfkit / wkhtmltopdf ===
    
    config = pdfkit.configuration(
        wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"  # ajusta se precisa
    )
    options = {
        "page-size": "A4",
        "orientation": "Landscape",
        "margin-top": "12mm",
        "margin-right": "10mm",
        "margin-bottom": "12mm",
        "margin-left": "10mm",
        "encoding": "UTF-8",
        "enable-local-file-access": "",                # permite file://
        "footer-center": "Página [page] de [toPage]",  # paginação rodapé
        "footer-font-size": "9",
        "quiet": "",
    }

    pdf_bytes = pdfkit.from_string(html_str, False, options=options, configuration=config)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": 'inline; filename="relatorio_reclamacoes.pdf"'}
    )

@app.route("/admin/relatorios/geral")
@require_roles({"admin_geral","admin"})
def relatorio_geral():
    log_acao("ver", "relatorio_geral")
    db = get_db()

    # --- filtros (iguais nos 2 tipos) ---
    data_inicio = request.args.get("data_inicio")
    data_fim    = request.args.get("data_fim")
    mes         = request.args.get("mes")          # YYYY-MM
    tipo        = request.args.get("tipo")
    estado      = request.args.get("estado")
    delegacao   = request.args.get("delegacao")

    # constrói WHERE + params para uma tabela qualquer com alias dado (ex.: 'd.' ou 'r.')
    def build_where(alias: str):
        where = ["1=1"]
        params = []

        # mês (se não houver data_inicio/data_fim)
        if mes and not (data_inicio or data_fim):
            try:
                dt_ini = datetime.strptime(mes + "-01", "%Y-%m-%d").date()
                if dt_ini.month == 12:
                    dt_fim = dt_ini.replace(year=dt_ini.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    dt_fim = dt_ini.replace(month=dt_ini.month + 1, day=1) - timedelta(days=1)
                where.append(f"date({alias}data_submissao) BETWEEN date(?) AND date(?)")
                params.extend([dt_ini.isoformat(), dt_fim.isoformat()])
            except ValueError:
                pass

        # intervalo de datas (pela submissão)
        if data_inicio:
            try:
                datetime.strptime(data_inicio, "%Y-%m-%d")
                where.append(f"date({alias}data_submissao) >= date(?)")
                params.append(data_inicio)
            except ValueError:
                pass
        if data_fim:
            try:
                datetime.strptime(data_fim, "%Y-%m-%d")
                where.append(f"date({alias}data_submissao) <= date(?)")
                params.append(data_fim)
            except ValueError:
                pass

        # tipo / estado
        if tipo:
            where.append(f"{alias}tipo = ?")
            params.append(tipo)
        if estado:
            where.append(f"{alias}estado = ?")
            params.append(estado)

        # delegação: nome (dg.nome) ou valor em delegacao_id
        if delegacao:
            where.append(
                f"(LOWER(COALESCE(dg.nome, '')) = LOWER(?) OR LOWER(CAST({alias}delegacao_id AS TEXT)) = LOWER(?))"
            )
            params.extend([delegacao, delegacao])

        return " AND ".join(where), params

    # monta as duas partes (denúncias + reclamações)
    where_d, params_d = build_where("d.")
    where_r, params_r = build_where("r.")

    sql = f"""
      SELECT 
        'denuncia' AS origem,
        d.codigo_acomp,
        d.tipo,
        d.data_submissao,
        d.data_ocorrencia,
        d.estado,
        COALESCE(dg.nome, d.delegacao_id) AS delegacao
      FROM denuncias d
      LEFT JOIN delegacoes dg
             ON d.delegacao_id = dg.id
             OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(dg.nome)
      WHERE {where_d}

      UNION ALL

      SELECT 
        'reclamacao' AS origem,
        r.codigo_acomp,
        r.tipo,
        r.data_submissao,
        r.data_ocorrencia,
        r.estado,
        COALESCE(dg2.nome, r.delegacao_id) AS delegacao
      FROM reclamacoes r
      LEFT JOIN delegacoes dg2
             ON r.delegacao_id = dg2.id
             OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(dg2.nome)
      WHERE {where_r}

      ORDER BY data_submissao DESC
    """

    rows = db.execute(sql, params_d + params_r).fetchall()

    return render_template(
        "admin/relatorio_geral.html",
        linhas=rows  # lista combinada
    )

@app.route("/admin/relatorios/geral/pdf")
@require_roles({"admin_geral","admin"})
def relatorio_geral_pdf():
    db = get_db()

    # filtros
    data_inicio = request.args.get("data_inicio")
    data_fim    = request.args.get("data_fim")
    mes         = request.args.get("mes")
    tipo        = request.args.get("tipo")
    estado      = request.args.get("estado")
    delegacao   = request.args.get("delegacao")

    def build_where(alias: str):
        where = ["1=1"]
        params = []
        if mes and not (data_inicio or data_fim):
            try:
                dt_ini = datetime.strptime(mes + "-01", "%Y-%m-%d").date()
                if dt_ini.month == 12:
                    dt_fim = dt_ini.replace(year=dt_ini.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    dt_fim = dt_ini.replace(month=dt_ini.month + 1, day=1) - timedelta(days=1)
                where.append(f"date({alias}data_submissao) BETWEEN date(?) AND date(?)")
                params.extend([dt_ini.isoformat(), dt_fim.isoformat()])
            except ValueError:
                pass
        if data_inicio:
            try:
                datetime.strptime(data_inicio, "%Y-%m-%d")
                where.append(f"date({alias}data_submissao) >= date(?)")
                params.append(data_inicio)
            except ValueError:
                pass
        if data_fim:
            try:
                datetime.strptime(data_fim, "%Y-%m-%d")
                where.append(f"date({alias}data_submissao) <= date(?)")
                params.append(data_fim)
            except ValueError:
                pass
        if tipo:
            where.append(f"{alias}tipo = ?")
            params.append(tipo)
        if estado:
            where.append(f"{alias}estado = ?")
            params.append(estado)
        if delegacao:
            where.append(f"(LOWER(COALESCE(dg.nome, '')) = LOWER(?) OR LOWER(CAST({alias}delegacao_id AS TEXT)) = LOWER(?))")
            params.extend([delegacao, delegacao])
        return " AND ".join(where), params

    where_d, params_d = build_where("d.")
    where_r, params_r = build_where("r.")

    sql = f"""
      SELECT 
        'denuncia' AS origem,
        d.codigo_acomp,
        d.tipo,
        d.data_submissao,
        d.data_ocorrencia,
        d.estado,
        COALESCE(dg.nome, d.delegacao_id) AS delegacao
      FROM denuncias d
      LEFT JOIN delegacoes dg
             ON d.delegacao_id = dg.id
             OR LOWER(CAST(d.delegacao_id AS TEXT)) = LOWER(dg.nome)
      WHERE {where_d}

      UNION ALL

      SELECT 
        'reclamacao' AS origem,
        r.codigo_acomp,
        r.tipo,
        r.data_submissao,
        r.data_ocorrencia,
        r.estado,
        COALESCE(dg2.nome, r.delegacao_id) AS delegacao
      FROM reclamacoes r
      LEFT JOIN delegacoes dg2
             ON r.delegacao_id = dg2.id
             OR LOWER(CAST(r.delegacao_id AS TEXT)) = LOWER(dg2.nome)
      WHERE {where_r}

      ORDER BY data_submissao DESC
    """
    linhas = db.execute(sql, params_d + params_r).fetchall()

    # KPIs globais e por origem
    total              = len(linhas)
    pendentes          = sum(1 for x in linhas if (x["estado"] or "pendente") == "pendente")
    em_analise         = sum(1 for x in linhas if x["estado"] == "em_analise")
    concluidas         = sum(1 for x in linhas if x["estado"] == "concluida")
    arquivadas         = sum(1 for x in linhas if x["estado"] == "arquivada")
    total_denuncias    = sum(1 for x in linhas if x["origem"] == "denuncia")
    total_reclamacoes  = sum(1 for x in linhas if x["origem"] == "reclamacao")

    kpis = {
        "total": total,
        "pendentes": pendentes,
        "em_analise": em_analise,
        "concluidas": concluidas,
        "arquivadas": arquivadas,
        "total_denuncias": total_denuncias,
        "total_reclamacoes": total_reclamacoes
    }

    gerado_em = datetime.now(pytz.timezone("Africa/Maputo")).strftime("%d/%m/%Y %H:%M")
    filtros = {
        "mes": mes,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipo": tipo,
        "estado": estado,
        "delegacao": delegacao
    }

    # logo local
    logo_file = Path(app.static_folder) / "img" / "logo.png"
    logo_src = logo_file.as_uri() if logo_file.exists() else None

    html_str = render_template(
        "admin/relatorio_geral_pdf.html",
        linhas=linhas,
        gerado_em=gerado_em,
        filtros=filtros,
        kpis=kpis,
        logo_src=logo_src
    )

    config = pdfkit.configuration(
        wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    )
    options = {
        "page-size": "A4",
        "orientation": "Landscape",
        "margin-top": "12mm",
        "margin-right": "10mm",
        "margin-bottom": "12mm",
        "margin-left": "10mm",
        "encoding": "UTF-8",
        "enable-local-file-access": "",
        "footer-center": "Página [page] de [toPage]",
        "footer-font-size": "9",
        "quiet": "",
    }

    pdf_bytes = pdfkit.from_string(html_str, False, options=options, configuration=config)
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="relatorio_geral.pdf"'})




@app.route("/admin/perfil")
@login_required
def perfil():
    db = get_db()
    u = db.execute("SELECT * FROM usuarios WHERE id = ?", (session["user_id"],)).fetchone()
    # pega nome da delegação
    delegacao_nome = None
    if u and u["delegacao_id"]:
        row = db.execute("SELECT nome FROM delegacoes WHERE id = ?", (u["delegacao_id"],)).fetchone()
        delegacao_nome = row["nome"] if row else None
    return render_template("admin/perfil.html", u=u, delegacao_nome=delegacao_nome)


@app.route("/admin/perfil/editar", methods=["POST"])
@login_required
def perfil_editar():
    db = get_db()
    nome = request.form.get("nome") or ""
    cargo = request.form.get("cargo") or ""
    db.execute("""
        UPDATE usuarios SET nome=?, cargo=? WHERE id=?
    """, (nome, cargo, session["user_id"]))
    db.commit()
    log_acao("editar_perfil", "usuarios")
    return redirect(url_for("perfil"))


@app.route("/admin/perfil/alterar_senha", methods=["POST"])
@login_required
def perfil_alterar_senha():
    db = get_db()
    atual = request.form.get("senha_atual") or ""
    nova  = request.form.get("senha_nova") or ""
    nova2 = request.form.get("senha_nova2") or ""

    u = db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()
    if not u:
        return "Utilizador não encontrado", 404

    if hashlib.sha256(atual.encode()).hexdigest() != u["senha"]:
        return "Senha atual incorreta", 400
    if not nova or nova != nova2:
        return "Nova senha inválida", 400

    db.execute("UPDATE usuarios SET senha=? WHERE id=?", (hashlib.sha256(nova.encode()).hexdigest(), session["user_id"]))
    db.commit()
    log_acao("alterar_senha", "usuarios")
    return redirect(url_for("perfil"))


@app.route("/admin/usuarios")
@login_required
@require_profiles(PERFIS["USUARIOS_ADMIN"])
def usuarios_listar():
    db = get_db()
    us = db.execute("""
        SELECT u.*, dg.nome AS delegacao_nome
        FROM usuarios u
        LEFT JOIN delegacoes dg ON dg.id = u.delegacao_id
        ORDER BY u.id DESC
    """).fetchall()
    log_acao("listar", "usuarios")
    return render_template("admin/usuarios.html", usuarios=us)


@app.route("/admin/usuarios/novo", methods=["GET", "POST"])
@login_required
@require_profiles(PERFIS["USUARIOS_ADMIN"])
def usuarios_novo():
    db = get_db()
    if request.method == "POST":
        nome  = request.form.get("nome")
        email = request.form.get("email")
        senha = request.form.get("senha")
        perfil= request.form.get("perfil")
        cargo = request.form.get("cargo") or ""
        deleg = request.form.get("delegacao_id") or None

        if not (nome and email and senha and perfil):
            return "Preencha os campos obrigatórios", 400

        senha_hash = hashlib.sha256(senha.encode()).hexdigest()
        cur = db.execute("""
            INSERT INTO usuarios (nome, email, senha, cargo, delegacao_id, perfil, ativo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (nome, email, senha_hash, cargo, deleg, perfil))
        db.commit()
        novo_uid = cur.lastrowid

        # salva tipos de reclamação se aplicável
        if perfil == "reclamacoes":
            rec_tipos = request.form.getlist("rec_tipos[]") or []
            if rec_tipos:
                db.executemany(
                    "INSERT INTO user_reclamacao_tipos (user_id, tipo) VALUES (?, ?)",
                    [(novo_uid, t) for t in rec_tipos]
                )
                db.commit()

        log_acao("criar", "usuarios")
        return redirect(url_for("usuarios_listar"))

    delegs = get_db().execute("SELECT id, nome FROM delegacoes ORDER BY nome").fetchall()
    return render_template(
        "admin/usuarios_novo.html",
        delegacoes=delegs,
        tipos_rec_groups=TIPOS_REC_GROUPS,
        modo="novo",
        u=None,
        selected_rec_tipos=set()
    )

@app.route("/admin/usuarios/<int:uid>/editar", methods=["GET", "POST"])
@login_required
@require_profiles(PERFIS["USUARIOS_ADMIN"])
def usuarios_editar(uid):
    db = get_db()
    u = db.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not u:
        return "Utilizador não encontrado", 404

    if request.method == "POST":
        nome   = request.form.get("nome")
        email  = request.form.get("email")
        perfil = request.form.get("perfil")
        cargo  = request.form.get("cargo") or ""
        deleg  = request.form.get("delegacao_id") or None
        # senha é opcional em edição
        senha  = request.form.get("senha") or ""

        if not (nome and email and perfil):
            return "Preencha os campos obrigatórios", 400

        if senha.strip():
            senha_hash = hashlib.sha256(senha.encode()).hexdigest()
            db.execute("""UPDATE usuarios
                          SET nome=?, email=?, senha=?, cargo=?, delegacao_id=?, perfil=?
                          WHERE id=?""",
                       (nome, email, senha_hash, cargo, deleg, perfil, uid))
        else:
            db.execute("""UPDATE usuarios
                          SET nome=?, email=?, cargo=?, delegacao_id=?, perfil=?
                          WHERE id=?""",
                       (nome, email, cargo, deleg, perfil, uid))
        db.commit()

        # atualiza tipos se perfil=reclamacoes; limpa senão
        db.execute("DELETE FROM user_reclamacao_tipos WHERE user_id=?", (uid,))
        if perfil == "reclamacoes":
            rec_tipos = request.form.getlist("rec_tipos[]") or []
            if rec_tipos:
                db.executemany(
                    "INSERT INTO user_reclamacao_tipos (user_id, tipo) VALUES (?, ?)",
                    [(uid, t) for t in rec_tipos]
                )
        db.commit()

        log_acao("editar", "usuarios")
        return redirect(url_for("usuarios_listar"))

    delegs = db.execute("SELECT id, nome FROM delegacoes ORDER BY nome").fetchall()
    selected = set(t["tipo"] for t in db.execute(
        "SELECT tipo FROM user_reclamacao_tipos WHERE user_id=?", (uid,)
    ).fetchall())

    return render_template(
        "admin/usuarios_novo.html",
        delegacoes=delegs,
        tipos_rec_groups=TIPOS_REC_GROUPS,
        modo="editar",
        u=u,
        selected_rec_tipos=selected
    )



@app.route("/admin/usuarios/<int:uid>/ativar", methods=["POST"])
@login_required
@require_profiles(PERFIS["USUARIOS_ADMIN"])
def usuarios_ativar(uid):
    db = get_db()
    db.execute("UPDATE usuarios SET ativo=1 WHERE id=?", (uid,))
    db.commit()
    log_acao("ativar", "usuarios")
    return redirect(url_for("usuarios_listar"))

@app.route("/admin/usuarios/<int:uid>/desativar", methods=["POST"])
@login_required
@require_profiles(PERFIS["USUARIOS_ADMIN"])
def usuarios_desativar(uid):
    db = get_db()
    db.execute("UPDATE usuarios SET ativo=0 WHERE id=?", (uid,))
    db.commit()
    log_acao("desativar", "usuarios")
    return redirect(url_for("usuarios_listar"))

@app.route("/admin/perfil/foto", methods=["POST"])
@login_required
def perfil_upload_foto():
    f = request.files.get("foto")
    if not f or f.filename == "" or not ext_ok(f.filename):
        return redirect(url_for("perfil"))

    # nome seguro + único
    base = secure_filename(f.filename)
    ext  = base.rsplit(".",1)[1].lower()
    new_name = f"user_{session['user_id']}_{int(datetime.now().timestamp())}.{ext}"
    save_path = os.path.join(AVATAR_FOLDER, new_name)
    f.save(save_path)

    # caminho relativo para usar no url_for('static', filename=...)
    rel_path = f"avatars/{new_name}"

    db = get_db()
    # garante que a coluna 'foto' existe (ver nota de schema abaixo)
    db.execute("UPDATE usuarios SET foto=? WHERE id=?", (rel_path, session["user_id"]))
    db.commit()
    log_acao("upload_foto", "usuarios")
    return redirect(url_for("perfil"))

if __name__ == "__main__":
    app.run(debug=True)
