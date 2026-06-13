import os
import pandas as pd
from groq import Groq
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===================== CONFIGURACIÓN =====================
load_dotenv()

GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")

GROQ_MODEL               = "llama-3.3-70b-versatile"
TIEMPO_EXPIRACION_MIN    = 60   # Minutos antes de reiniciar contexto
LIMITE_CONTEXTO          = 5    # Número de intercambios anteriores a incluir
HISTORIAL_EXCEL          = "historial_conversaciones.xlsx"
COLUMNAS                 = ["ID Usuario", "Nombre Usuario", "Fecha y Hora", "Pregunta", "Respuesta"]

AVISO_LEGAL = (
    "⚠️ *Aviso legal:* Este chatbot brinda orientación laboral básica e informativa. "
    "No reemplaza la asesoría jurídica profesional ni constituye representación legal. "
    "Para casos específicos, consulte a un abogado laboralista."
)

cliente = Groq(api_key=GROQ_API_KEY)

# ===================== EXCEL =====================
def asegurar_excel() -> None:
    """Crea el archivo Excel si no existe o si le faltan columnas."""
    if not os.path.exists(HISTORIAL_EXCEL):
        pd.DataFrame(columns=COLUMNAS).to_excel(HISTORIAL_EXCEL, index=False)
        return
    try:
        df = pd.read_excel(HISTORIAL_EXCEL)
        if not all(col in df.columns for col in COLUMNAS):
            pd.DataFrame(columns=COLUMNAS).to_excel(HISTORIAL_EXCEL, index=False)
    except Exception:
        pd.DataFrame(columns=COLUMNAS).to_excel(HISTORIAL_EXCEL, index=False)

def cargar_historial() -> pd.DataFrame:
    asegurar_excel()
    df = pd.read_excel(HISTORIAL_EXCEL)
    df["Fecha y Hora"] = pd.to_datetime(df["Fecha y Hora"], errors="coerce")
    return df

def registrar_en_excel(user_id: str, nombre: str, pregunta: str, respuesta: str) -> None:
    nuevo = pd.DataFrame([{
        "ID Usuario":     user_id,
        "Nombre Usuario": nombre,
        "Fecha y Hora":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Pregunta":       pregunta,
        "Respuesta":      respuesta,
    }])
    historial = cargar_historial()
    pd.concat([historial, nuevo], ignore_index=True).to_excel(HISTORIAL_EXCEL, index=False)

# ===================== CONTEXTO =====================
def obtener_contexto(usuario_id: str, historial: pd.DataFrame) -> str:
    """
    Devuelve las últimas N interacciones del usuario.
    Retorna cadena vacía si el último mensaje fue hace más de TIEMPO_EXPIRACION_MIN.
    """
    hist_usuario = historial[historial["ID Usuario"].astype(str) == str(usuario_id)]
    if hist_usuario.empty:
        return ""

    ultima_fecha = hist_usuario["Fecha y Hora"].max()
    if pd.isnull(ultima_fecha):
        return ""

    if datetime.now() - ultima_fecha > timedelta(minutes=TIEMPO_EXPIRACION_MIN):
        return ""   # Contexto expirado → conversación nueva

    recientes = hist_usuario.tail(LIMITE_CONTEXTO)
    return "\n".join(
        f"Usuario: {r['Pregunta']}\nAsistente: {r['Respuesta']}"
        for _, r in recientes.iterrows()
    )

# ===================== GROQ =====================
def consultar_groq(contexto: str, pregunta: str) -> str:
    """Arma el prompt especializado en derecho laboral colombiano y llama a la API de Groq."""
    system_prompt = (
        "Eres un orientador jurídico laboral virtual especializado en derecho laboral colombiano. "
        "Tu función es brindar orientación laboral básica e informativa sobre los siguientes temas:\n"
        "- Contratos laborales (tipos, cláusulas, terminación)\n"
        "- Liquidaciones de prestaciones sociales\n"
        "- Cesantías e intereses de cesantías\n"
        "- Vacaciones (cálculo, acumulación, compensación)\n"
        "- Incapacidades (laborales, de origen común, licencias)\n"
        "- Despidos (justas causas, indemnizaciones, procedimientos)\n"
        "- Derechos laborales básicos (salario mínimo, jornada laboral, horas extras, seguridad social, prima de servicios)\n\n"
        "Reglas que debes seguir:\n"
        "1. Responde de forma clara, simple y concisa (máximo 8 líneas).\n"
        "2. Usa lenguaje accesible, evitando tecnicismos innecesarios.\n"
        "3. Cuando sea pertinente, cita el artículo o norma legal colombiana aplicable "
        "(Código Sustantivo del Trabajo, leyes complementarias).\n"
        "4. NO des asesoría legal especializada ni representación jurídica.\n"
        "5. Siempre aclara que tu orientación es informativa y no reemplaza la consulta con un abogado.\n"
        "6. Si la pregunta NO está relacionada con temas laborales, indícalo amablemente "
        "y redirige al usuario a formular preguntas sobre derechos laborales.\n"
        "7. Si la consulta requiere atención profesional, sugiere acudir al Ministerio del Trabajo, "
        "a un consultorio jurídico universitario o a un abogado laboralista.\n"
        "8. No incluyas saludos ni frases de cierre."
    )

    mensajes = [{"role": "system", "content": system_prompt}]

    # Inyectar contexto como turnos previos de la conversación
    if contexto:
        for linea in contexto.strip().split("\n"):
            if linea.startswith("Usuario: "):
                mensajes.append({"role": "user",      "content": linea[len("Usuario: "):]})
            elif linea.startswith("Asistente: "):
                mensajes.append({"role": "assistant", "content": linea[len("Asistente: "):]})

    mensajes.append({"role": "user", "content": pregunta})

    respuesta = cliente.chat.completions.create(
        model=GROQ_MODEL,
        messages=mensajes,
        max_tokens=512,
        temperature=0.4,
    )
    return respuesta.choices[0].message.content.strip()

# ===================== HANDLERS TELEGRAM =====================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⚖️ *Bienvenido al Chatbot de Orientación Jurídica Laboral*\n\n"
        "Soy un asistente virtual que te brinda orientación básica sobre "
        "derechos laborales en Colombia.\n\n"
        "📋 Puedo ayudarte con consultas sobre:\n"
        "• Contratos laborales\n"
        "• Liquidaciones\n"
        "• Cesantías\n"
        "• Vacaciones\n"
        "• Incapacidades\n"
        "• Despidos\n"
        "• Derechos laborales básicos\n\n"
        "Escribe tu pregunta y te responderé de inmediato.\n\n"
        + AVISO_LEGAL,
        parse_mode="Markdown",
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Comandos disponibles:*\n\n"
        "/start — Inicia el bot y muestra la bienvenida\n"
        "/help  — Muestra esta ayuda\n"
        "/temas — Lista los temas sobre los que puedo orientarte\n"
        "/aviso — Muestra el aviso legal\n\n"
        "💡 Simplemente escribe tu pregunta sobre temas laborales "
        "y recibirás una respuesta informativa.",
        parse_mode="Markdown",
    )

async def cmd_temas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 *Temas de orientación laboral disponibles:*\n\n"
        "1️⃣ *Contratos laborales* — Tipos, cláusulas, terminación\n"
        "2️⃣ *Liquidaciones* — Cálculo de prestaciones sociales\n"
        "3️⃣ *Cesantías* — Cesantías e intereses de cesantías\n"
        "4️⃣ *Vacaciones* — Cálculo, acumulación, compensación\n"
        "5️⃣ *Incapacidades* — Laborales, de origen común, licencias\n"
        "6️⃣ *Despidos* — Justas causas, indemnizaciones, procedimientos\n"
        "7️⃣ *Derechos básicos* — Salario mínimo, jornada, horas extras, "
        "seguridad social, prima de servicios\n\n"
        "Escribe tu pregunta sobre cualquiera de estos temas.",
        parse_mode="Markdown",
    )

async def cmd_aviso(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(AVISO_LEGAL, parse_mode="Markdown")

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id  = str(update.message.from_user.id)
    nombre   = update.message.from_user.first_name or "Usuario"
    pregunta = update.message.text.strip()

    if not pregunta:
        return

    historial = cargar_historial()
    contexto  = obtener_contexto(user_id, historial)

    try:
        texto = consultar_groq(contexto, pregunta)
    except Exception as e:
        texto = f"❌ Error al procesar la consulta: {e}"

    registrar_en_excel(user_id, nombre, pregunta, texto)
    await update.message.reply_text(texto)

# ===================== MAIN =====================
def main() -> None:
    if not GROQ_API_KEY or not TELEGRAM_TOKEN:
        raise ValueError("Faltan variables de entorno: GROQ_API_KEY y/o TELEGRAM_TOKEN")

    asegurar_excel()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("temas", cmd_temas))
    app.add_handler(CommandHandler("aviso", cmd_aviso))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("⚖️ Chatbot de Orientación Jurídica Laboral ejecutándose... Ctrl+C para detener.")
    app.run_polling()

if __name__ == "__main__":
    main()

