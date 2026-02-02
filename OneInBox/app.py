from flask import Flask, render_template, jsonify, request
import json
import os
import random
from datetime import datetime

app = Flask(__name__)
DATA_FILE = "data.json"

# Mensajes de ejemplo (CORREGIDO ENCODING)
EXAMPLE_MESSAGES = [
    "¿Cuál es el precio?", 
    "¿Horarios de atención?", 
    "¿Tienen envío?", 
    "¿Hay disponibilidad?", 
    "¿Cuál es el stock?",
    "Hola, necesito ayuda",
    "Gracias por la información",
    "¿Aceptan tarjetas?",
    "¿Hacen delivery?",
    "¿Tienen promociones?"
]

# Nombres random de clientes (CORREGIDO)
CUSTOMERS = [
    "Ana García", "Juan Pérez", "Carlos López", "María Rodríguez", 
    "Luis Martínez", "Sofía González", "Diego Fernández", 
    "Valentina Silva", "Pedro Ramírez", "Camila Torres"
]

# Plataformas con iconos y gradientes
PLATFORMS = [
    {"name": "WhatsApp", "color": "green", "icon": "💬", "gradient": "from-green-400 to-green-600"},
    {"name": "Facebook", "color": "blue", "icon": "👍", "gradient": "from-blue-400 to-blue-600"},
    {"name": "Instagram", "color": "violet", "icon": "📷", "gradient": "from-purple-400 via-pink-500 to-red-500"}
]

# Reglas automáticas de respuestas (AMPLIADAS)
RULES = [
    {"keyword": "precio", "response": "💰 Nuestros precios empiezan desde $10. ¿Te interesa algún producto en particular?"},
    {"keyword": "horario", "response": "🕐 Atendemos de Lunes a Viernes de 8:00 a 18:00 hs. ¡Estamos para ayudarte!"},
    {"keyword": "envío", "response": "📦 El envío está incluido en todas las compras. Llegamos a todo el país."},
    {"keyword": "stock", "response": "✅ Tenemos stock disponible de todos los productos. ¿Cuál te interesa?"},
    {"keyword": "disponibilidad", "response": "✅ Todos los productos están disponibles para entrega inmediata."},
    {"keyword": "hola", "response": "👋 ¡Hola! Bienvenido. ¿En qué puedo ayudarte hoy?"},
    {"keyword": "gracias", "response": "😊 ¡De nada! ¿Hay algo más en lo que pueda ayudarte?"},
    {"keyword": "tarjeta", "response": "💳 Aceptamos todas las tarjetas de crédito y débito. También Mercado Pago."},
    {"keyword": "delivery", "response": "🚗 Sí, hacemos delivery a domicilio. El tiempo estimado es de 30-45 minutos."},
    {"keyword": "promocion", "response": "🎉 Tenemos 20% OFF en productos seleccionados. ¡Aprovecha!"}
]

# ------------------------
# Guardar y cargar data
# ------------------------
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_data():
    if not os.path.exists(DATA_FILE):
        save_data({"messages": [], "stats": {"total": 0, "whatsapp": 0, "facebook": 0, "instagram": 0}})
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Inicializar con datos limpios
if not os.path.exists(DATA_FILE):
    save_data({"messages": [], "stats": {"total": 0, "whatsapp": 0, "facebook": 0, "instagram": 0}})

# ------------------------
# Rutas Flask
# ------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/messages")
def get_messages():
    data = load_data()
    return jsonify(data.get("messages", []))

@app.route("/api/stats")
def get_stats():
    """Nueva ruta para estadísticas"""
    data = load_data()
    messages = data.get("messages", [])
    
    # Calcular estadísticas
    stats = {
        "total": len(messages),
        "whatsapp": len([m for m in messages if m.get("platform") == "WhatsApp"]),
        "facebook": len([m for m in messages if m.get("platform") == "Facebook"]),
        "instagram": len([m for m in messages if m.get("platform") == "Instagram"]),
        "user_messages": len([m for m in messages if m.get("type") == "user"]),
        "bot_responses": len([m for m in messages if m.get("type") == "bot"])
    }
    
    return jsonify(stats)

@app.route("/api/generate")
def generate_message():
    """Generar mensaje automático (tu código mejorado)"""
    data = load_data()

    # Crear mensaje random
    customer = random.choice(CUSTOMERS)
    platform = random.choice(PLATFORMS)
    content = random.choice(EXAMPLE_MESSAGES)
    time = datetime.now().strftime("%H:%M:%S")

    msg = {
        "id": len(data.get("messages", [])) + 1,
        "platform": platform["name"],
        "color": platform["color"],
        "icon": platform["icon"],
        "gradient": platform["gradient"],
        "customer": customer,
        "content": content,
        "time": time,
        "type": "user",
        "timestamp": datetime.now().isoformat()
    }

    data["messages"].append(msg)

    # Generar respuesta automática (mejorada)
    response_generated = False
    for rule in RULES:
        if rule["keyword"].lower() in content.lower():
            bot_msg = {
                "id": len(data["messages"]) + 1,
                "platform": "Bot",
                "color": "green",
                "icon": "🤖",
                "gradient": "from-green-400 to-emerald-600",
                "customer": "AutoBot",
                "content": rule["response"],
                "time": time,
                "type": "bot",
                "timestamp": datetime.now().isoformat()
            }
            data["messages"].append(bot_msg)
            response_generated = True
            break
    
    # Si no hay regla, respuesta genérica
    if not response_generated:
        bot_msg = {
            "id": len(data["messages"]) + 1,
            "platform": "Bot",
            "color": "green",
            "icon": "🤖",
            "gradient": "from-green-400 to-emerald-600",
            "customer": "AutoBot",
            "content": "Gracias por tu mensaje. Un agente te responderá pronto. 😊",
            "time": time,
            "type": "bot",
            "timestamp": datetime.now().isoformat()
        }
        data["messages"].append(bot_msg)

    save_data(data)
    return jsonify({"status": "ok", "message": msg, "response": bot_msg})

@app.route("/api/send", methods=["POST"])
def send_message():
    """Nueva ruta: Enviar mensaje manual desde el simulador"""
    data = load_data()
    req_data = request.json
    
    platform_name = req_data.get("platform", "WhatsApp")
    content = req_data.get("message", "")
    customer_name = req_data.get("customer", "Usuario Demo")
    
    # Encontrar info de la plataforma
    platform = next((p for p in PLATFORMS if p["name"] == platform_name), PLATFORMS[0])
    
    time = datetime.now().strftime("%H:%M:%S")
    
    # Mensaje del usuario
    user_msg = {
        "id": len(data.get("messages", [])) + 1,
        "platform": platform["name"],
        "color": platform["color"],
        "icon": platform["icon"],
        "gradient": platform["gradient"],
        "customer": customer_name,
        "content": content,
        "time": time,
        "type": "user",
        "timestamp": datetime.now().isoformat()
    }
    
    data["messages"].append(user_msg)
    
    # Buscar respuesta automática
    bot_response = "Gracias por tu mensaje. Un agente te responderá pronto. 😊"
    for rule in RULES:
        if rule["keyword"].lower() in content.lower():
            bot_response = rule["response"]
            break
    
    # Respuesta del bot
    bot_msg = {
        "id": len(data["messages"]) + 1,
        "platform": "Bot",
        "color": "green",
        "icon": "🤖",
        "gradient": "from-green-400 to-emerald-600",
        "customer": "AutoBot",
        "content": bot_response,
        "time": time,
        "type": "bot",
        "timestamp": datetime.now().isoformat()
    }
    
    data["messages"].append(bot_msg)
    save_data(data)
    
    return jsonify({"status": "ok", "user_message": user_msg, "bot_response": bot_msg})

@app.route("/api/clear", methods=["POST"])
def clear_messages():
    """Nueva ruta: Limpiar todos los mensajes"""
    save_data({"messages": [], "stats": {"total": 0, "whatsapp": 0, "facebook": 0, "instagram": 0}})
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 OneInBox - Sistema de Mensajería Automatizada")
    print("=" * 60)
    print("📱 Dashboard: http://localhost:5000")
    print("🤖 Generación automática: Cada 5 segundos")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
