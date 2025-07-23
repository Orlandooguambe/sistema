from flask import Flask, render_template, request, g
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


app = Flask(__name__)
DATABASE = "confidencia.db"
app.secret_key = 'segredo-super-seguro-123'
# Pasta para uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'mp3', 'wav', 'm4a', 'ogg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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

# Fechar a conexão após cada request
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

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
        prazo = adicionar_dias_uteis(hoje, 5)
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
        prazo = adicionar_dias_uteis(datetime.today(), 5).date()

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
    db = get_db()

    if request.method == "POST":
        codigo = request.form.get("codigo")
        mensagem = request.form.get("mensagem")

        if mensagem:
            db.execute("""
                INSERT INTO mensagens (codigo_acomp, conteudo, remetente, data_envio)
                VALUES (?, ?, 'colaborador', datetime('now'))
            """, (codigo, mensagem))
            db.commit()

        # Buscar novamente após envio
        denuncia = db.execute("SELECT * FROM denuncias WHERE codigo_acomp = ?", (codigo,)).fetchone()
        if denuncia:
            mensagens = db.execute("SELECT * FROM mensagens WHERE codigo_acomp = ? ORDER BY data_envio ASC", (codigo,)).fetchall()
            return render_template("public/acompanhamento.html", resultado=denuncia, mensagens=mensagens, tipo="denuncia", tentativa=True)

        reclamacao = db.execute("SELECT * FROM reclamacoes WHERE codigo_acomp = ?", (codigo,)).fetchone()
        if reclamacao:
            mensagens = db.execute("SELECT * FROM mensagens WHERE codigo_acomp = ? ORDER BY data_envio ASC", (codigo,)).fetchall()
            return render_template("public/acompanhamento.html", resultado=reclamacao, mensagens=mensagens, tipo="reclamacao", tentativa=True)

        return render_template("public/acompanhamento.html", resultado=None, tentativa=True)

    return render_template("public/acompanhamento.html", resultado=None, tentativa=False)

@app.route("/responder", methods=["POST"])
def responder():
    db = get_db()
    codigo = request.form.get("codigo")
    conteudo = request.form.get("mensagem")

    if codigo and conteudo:
        db.execute("""
            INSERT INTO mensagens (codigo_acomp, conteudo, remetente, data_envio)
            VALUES (?, ?, 'cidadao', datetime('now'))
        """, (codigo, conteudo))
        db.commit()

    return redirect(url_for("acompanhamento"))



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
def painel():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("admin/index.html")



@app.route("/admin/denuncias")
def ver_denuncias():
    db = get_db()
    tipo = request.args.get("tipo")
    estado = request.args.get("estado")
    data = request.args.get("data")

    query = "SELECT * FROM denuncias WHERE 1=1"
    params = []

    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)

    # Lógica especial para 'pendente' (estado NULL ou vazio)
    if estado:
       query += " AND estado = ?"
       params.append(estado)

    elif estado:
        query += " AND estado = ?"
        params.append(estado)

    if data:
        query += " AND date(data_submissao) = ?"
        params.append(data)

    denuncias = db.execute(query + " ORDER BY data_submissao DESC", params).fetchall()

    total = db.execute("SELECT COUNT(*) FROM denuncias").fetchone()[0]
    pendentes = db.execute("SELECT COUNT(*) FROM denuncias WHERE estado = 'pendente'").fetchone()[0]
    em_analise = db.execute("SELECT COUNT(*) FROM denuncias WHERE estado = 'em_analise'").fetchone()[0]
    concluidas = db.execute("SELECT COUNT(*) FROM denuncias WHERE estado = 'concluida'").fetchone()[0]
    arquivadas = db.execute("SELECT COUNT(*) FROM denuncias WHERE estado = 'arquivada'").fetchone()[0]

    return render_template("admin/ver_denuncias.html",
                           denuncias=denuncias,
                           total_denuncias=total,
                           pendentes=pendentes,
                           em_analise=em_analise,
                           concluidas=concluidas,
                           arquivadas=arquivadas,
                           tipo=tipo,
                           estado=estado,
                           data=data)


@app.route("/admin/denuncias/<int:id>", methods=["GET", "POST"])
def ver_detalhes_denuncia(id):
    db = get_db()
    denuncia = db.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()
    if not denuncia:
        return "Denúncia não encontrada", 404

    # Atualizar estado e/ou enviar resposta
    if request.method == "POST":
        novo_estado = request.form.get("novo_estado")
        resposta = request.form.get("resposta")

        if novo_estado:
            db.execute("UPDATE denuncias SET estado = ? WHERE id = ?", (novo_estado, id))
            db.commit()
            denuncia = db.execute("SELECT * FROM denuncias WHERE id = ?", (id,)).fetchone()

        if resposta:
            db.execute("""
                INSERT INTO mensagens (codigo_acomp, conteudo, remetente, data_envio)
                VALUES (?, ?, 'admin', datetime('now'))
            """, (denuncia["codigo_acomp"], resposta))
            db.commit()

    # Deserializar anexos
    anexos = []
    if denuncia["anexos"]:
        anexos = json.loads(denuncia["anexos"])

    mensagens = db.execute("""SELECT * FROM mensagens WHERE codigo_acomp = ? ORDER BY data_envio ASC """, (denuncia["codigo_acomp"],)).fetchall()

    return render_template("admin/ver_detalhes_denuncia.html",
                       denuncia=denuncia,
                       anexos=anexos,
                       mensagens=mensagens)



if __name__ == "__main__":
    app.run(debug=True)
