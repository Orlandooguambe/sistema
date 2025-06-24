# run.py
from flask import Flask, render_template, request
from datetime import date

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("public/base.html")

@app.route("/denuncia", methods=["GET", "POST"])
def denuncia():
    if request.method == "GET":
        return render_template("public/denuncia.html", current_date=date.today().isoformat())
    # Lógica de POST futura
    return "Formulário enviado"


@app.route("/reclamacao", methods=["GET", "POST"])
def reclamacao():
    if request.method == "GET":
        return render_template("public/reclamacao.html", current_date=date.today().isoformat())
    return "Reclamação submetida!"


@app.route("/acompanhamento", methods=["GET", "POST"])
def acompanhamento():
    if request.method == "POST":
        codigo = request.form.get("codigo")
        # Simulação de busca (depois vamos ligar à base de dados)
        if codigo == "ABC123XYZ":
            resultado = {
                "codigo": codigo,
                "estado": "Em análise",
                "historico": [
                    {"data": "2025-06-20", "texto": "Denúncia recebida."},
                    {"data": "2025-06-22", "texto": "Em verificação pela equipe de Compliance."}
                ]
            }
        else:
            resultado = None
        return render_template("public/acompanhamento.html", resultado=resultado, tentativa=True)

    return render_template("public/acompanhamento.html", resultado=None, tentativa=False)
@app.route("/ajuda")
def ajuda():
    return render_template("public/ajuda.html")


if __name__ == "__main__":
    app.run(debug=True)
