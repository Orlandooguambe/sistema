from flask import Flask, render_template, request, g
from datetime import date
import sqlite3
from uuid import uuid4
from flask import redirect, url_for, session
import secrets
from datetime import datetime, timedelta

app = Flask(__name__)
DATABASE = "confidencia.db"
app.secret_key = 'segredo-super-seguro-123'


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

        db.execute("""
            INSERT INTO denuncias (tipo, delegacao_id, descricao, data_ocorrencia, data_submissao, codigo_acomp, estado, prazo_resposta)
            VALUES (?, (SELECT id FROM delegacoes WHERE lower(nome)=?), ?, ?, datetime('now'), ?, 'em análise', ?)
        """, (tipo, delegacao.lower(), descricao, data_ocorrencia, codigo, prazo.isoformat()))
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
            "",  # anexos vazios por enquanto
            dados.get("data_ocorrencia"),
            codigo,
            dados.get("delegacao"),
            prazo
        ))
        db.commit()

        # Guarda o código e prazo na sessão para mostrar na página de sucesso
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
        codigo = request.form.get("codigo")
        db = get_db()

        # Tenta buscar primeiro em denúncias
        denuncia = db.execute("SELECT * FROM denuncias WHERE codigo_acomp = ?", (codigo,)).fetchone()
        if denuncia:
            mensagens = db.execute("SELECT * FROM mensagens WHERE codigo_acomp = ? ORDER BY data_envio ASC", (codigo,)).fetchall()
            return render_template("public/acompanhamento.html", resultado=denuncia, mensagens=mensagens, tipo="denuncia", tentativa=True)

        # Ou tenta buscar em reclamações
        reclamacao = db.execute("SELECT * FROM reclamacoes WHERE codigo_acomp = ?", (codigo,)).fetchone()
        if reclamacao:
            mensagens = db.execute("SELECT * FROM mensagens WHERE codigo_acomp = ? ORDER BY data_envio ASC", (codigo,)).fetchall()
            return render_template("public/acompanhamento.html", resultado=reclamacao, mensagens=mensagens, tipo="reclamacao", tentativa=True)

        return render_template("public/acompanhamento.html", resultado=None, tentativa=True)

    return render_template("public/acompanhamento.html", resultado=None, tentativa=False)

@app.route("/ajuda")
def ajuda():
    return render_template("public/ajuda.html")

if __name__ == "__main__":
    app.run(debug=True)
