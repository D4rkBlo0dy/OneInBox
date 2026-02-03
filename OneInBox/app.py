from flask import Flask, jsonify, request, render_template
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
import random, re, time, unicodedata
from typing import Dict, List, Optional, Tuple

app = Flask(__name__)

# =========================
# CONFIG (tocar acá)
# =========================
PLATFORMS = ["whatsapp", "instagram", "facebook"]
AUTO_USER = "Atención"
MSG_CAP, STATE_CAP = 400, 300  # caps de memoria

def L(s: str) -> List[str]:
    return [x.strip() for x in s.split("|") if x.strip()]

USERS = L("Sofía|Lucas|Valentina|Mateo|Camila|Diego|Ana|Bruno|María|Nico|Carla|Julián|Mica|Tomás|Paula|Fede|Mauri|Jime|Abi|Enzo|Gabi")

SEEDS = L(
    "Hola|Buenas|Buen día|Hola, ¿qué tal?"
    "|Quiero comprar algo|¿Tienen ropa?|Busco zapatillas|Necesito una mochila|Quiero ver opciones de remeras"
    "|Me llegó un cobro que no reconozco|Me cobraron dos veces|Quiero pedir un reembolso|Tengo una consulta por un pago"
    "|No puedo entrar a mi cuenta|Olvidé mi contraseña|Me pide un código y no me llega|Se me bloqueó la cuenta"
    "|¿Hay novedades de mi caso?|¿Cuánto tarda el proceso?|¿Me confirmás el estado del trámite?"
    "|No funciona, me da error|No me deja finalizar|Se me cae al abrir"
    "|Quiero actualizar mis datos|Necesito cambiar mi correo|Quiero modificar mi teléfono"
)

# =========================
# STORAGE (demo)
# =========================
MESSAGES: List[dict] = []
SEQ = 0

def next_seq():
    global SEQ
    SEQ += 1
    return SEQ

def iso_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower().strip()

def thread_id(platform: str, user: str) -> str:
    return f"{platform}:{norm(user)}"

def mk_msg(platform, role, user, text, t_id, reply_to=None):
    return {
        "id": str(uuid4()),
        "seq": next_seq(),
        "thread_id": t_id,
        "reply_to": reply_to,
        "platform": platform,
        "role": role,
        "user": user,
        "text": text,
        "timestamp": iso_now(),
    }

def clamp_memory(conv: Dict[str, "State"]):
    if len(MESSAGES) > MSG_CAP:
        del MESSAGES[:len(MESSAGES) - MSG_CAP]
    if len(conv) > STATE_CAP:
        # elimina los estados más viejos (LRU simple)
        for k, _ in sorted(conv.items(), key=lambda kv: kv[1].last_seen)[:len(conv) - STATE_CAP]:
            conv.pop(k, None)

# =========================
# Conversación (estado mínimo)
# =========================
@dataclass
class State:
    intent: Optional[str] = None
    user: str = "Usuario"
    slots: Dict[str, str] = field(default_factory=dict)   # datos recogidos (item, size, account, etc.)
    last_seen: float = field(default_factory=time.time)
    last_sig: List[str] = field(default_factory=list)     # anti-repetición

CONV: Dict[str, State] = {}

def remember_sig(st: State, sig: str):
    st.last_sig.append(sig)
    if len(st.last_sig) > 4:
        st.last_sig = st.last_sig[-4:]

def pick(pool: List[str], st: State, sig: str):
    # evita repetir el mismo “tipo de respuesta” varias veces seguidas
    last = st.last_sig[-1] if st.last_sig else None
    if last == sig and len(pool) > 1:
        opts = pool[1:]  # simple fallback
        out = random.choice(opts)
    else:
        out = random.choice(pool)
    remember_sig(st, sig)
    return out

def ticket(st: State) -> str:
    if "ticket" not in st.slots:
        st.slots["ticket"] = f"OIB-{random.randint(10000, 99999)}"
    return st.slots["ticket"]

# =========================
# Intents
# =========================
GREET, THANKS = "greet", "thanks"
PURCHASE, PAYMENT, LOGIN, STATUS, ISSUE, UPDATE, AMBIG, GENERAL = (
    "purchase", "payment", "login", "status", "issue", "update", "ambig", "general"
)

EMAIL_RE = re.compile(r"([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})")

KW = {
    PURCHASE: L("compr|precio|producto|ropa|remera|jean|pantal|buzo|zapat|mochila|talle|color|envio|envío|stock"),
    PAYMENT:  L("pago|cobro|factura|tarjeta|transfer|reembolso|reintegro|monto|importe|no reconozco|dos veces|duplic"),
    LOGIN:    L("acceso|entrar|login|contrase|contraseña|codigo|código|bloque|sesion|sesión|password"),
    STATUS:   L("estado|seguim|novedad|pendiente|demora|tarda|tramite|trámite|en que quedo|en qué quedó"),
    ISSUE:    L("problema|error|no funciona|fallo|bug|se cae|no me deja"),
    UPDATE:   L("actualiz|cambiar|modificar|datos|correo|email|telefono|teléfono|direccion|dirección|nombre"),
}

ITEM_WORDS = {
    "remeras": L("remera|remeras|camiseta|tshirt|t-shirt"),
    "jeans":   L("jean|jeans|pantalon|pantalón|pantalones"),
    "buzos":   L("buzo|hoodie|campera|sweater"),
    "zapatillas": L("zapatilla|zapatillas|zapato|zapatos|calzado"),
    "mochilas": L("mochila|bolso|cartera"),
    "ropa":    L("ropa|prenda|prendas"),
    "calzado": L("calzado|zapatos|zapatillas"),
    "accesorios": L("accesorio|accesorios|mochila|bolso|cartera"),
}

def is_greet(tn: str) -> bool:
    return tn in ["hola", "holi", "buenas", "buen dia", "buen día", "hey"] or tn.startswith("hola") or tn.startswith("buenas")

def is_thanks(tn: str) -> bool:
    return tn == "gracias" or tn.startswith("gracias")

def classify(tn: str, st: Optional[State]) -> str:
    # si estamos esperando un dato específico, mantenemos intent
    if st and st.intent and st.slots.get("_expect"):
        ex = st.slots["_expect"]
        got = extract(st.intent, tn).get(ex)
        if got:
            return st.intent

    if is_greet(tn): return GREET
    if is_thanks(tn): return THANKS
    if not tn or len(tn) < 3 or re.fullmatch(r"[?¿!\s]+", tn): return AMBIG

    scores = {k: 0 for k in KW.keys()}
    for intent, keys in KW.items():
        for kw in keys:
            if kw in tn:
                scores[intent] += 1

    best_intent, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_intent if best_score > 0 else GENERAL

# =========================
# Slots
# =========================
def extract(intent: str, tn: str) -> Dict[str, str]:
    out = {}

    if intent == PURCHASE:
        for item, words in ITEM_WORDS.items():
            if any(w in tn for w in words):
                out["item"] = item
                break

        m = re.search(r"\b(?:talle|size|numero|número)\s*[:\-]?\s*(xxs|xs|s|m|l|xl|xxl|xxxl|\d{1,3})\b", tn)
        if m:
            out["size"] = m.group(1).upper()

        m2 = re.search(r"(\$|usd|usdt|gs|₲)\s*([\d\.]{1,10})|([\d\.]{1,10})\s*(usd|usdt|gs)", tn)
        if m2:
            out["budget"] = m2.group(0).strip().upper()

    elif intent == PAYMENT:
        if "no reconozco" in tn: out["case"] = "no_reconocido"
        elif "dos veces" in tn or "duplic" in tn: out["case"] = "duplicado"
        elif "reembolso" in tn or "reintegro" in tn: out["case"] = "reembolso"

        m = re.search(r"\b([\d\.]{1,10})\s*(usd|usdt|gs)\b", tn)
        if m:
            out["amount"] = f"{m.group(1)} {m.group(2).upper()}"

    elif intent == LOGIN:
        if "contrase" in tn or "olvid" in tn: out["issue"] = "contraseña"
        elif "codigo" in tn or "código" in tn: out["issue"] = "código"
        elif "bloque" in tn: out["issue"] = "bloqueo"

        m = EMAIL_RE.search(tn)
        if m:
            out["account"] = m.group(1)

    elif intent == STATUS:
        m = re.search(r"\b(\d{4,})\b", tn)
        if m:
            out["ref"] = m.group(1)

    elif intent == UPDATE:
        if "correo" in tn or "email" in tn: out["field"] = "correo"
        elif "telefono" in tn or "teléfono" in tn: out["field"] = "teléfono"
        elif "direccion" in tn or "dirección" in tn: out["field"] = "dirección"
        elif "nombre" in tn: out["field"] = "nombre"
        m = EMAIL_RE.search(tn)
        if m:
            out["value"] = m.group(1)

    elif intent == ISSUE:
        # consideramos “details” si el mensaje no es trivial
        if len(tn) >= 6:
            out["details"] = "ok"

    return out

def next_missing(intent: str, slots: Dict[str, str]) -> Optional[str]:
    if intent == LOGIN:
        if not slots.get("issue"): return "issue"
        if slots.get("issue") in ["contraseña", "código", "bloqueo"] and not slots.get("account"):
            return "account"
        return None

    if intent == PAYMENT:
        if not slots.get("case"): return "case"
        if not slots.get("amount"): return "amount"
        return None

    if intent == PURCHASE:
        it = slots.get("item")
        if not it: return "item"
        if it in ["ropa", "calzado", "accesorios"]: return "refine"
        # si es ropa/calzado: pedir size, si no está
        if it in ["zapatillas", "remeras", "jeans", "buzos"] and not slots.get("size"):
            return "size"
        # pedir budget si no está (una vez)
        if not slots.get("budget") and not slots.get("_asked_budget"):
            return "budget"
        return None

    if intent == STATUS:
        if not slots.get("ref"): return "ref"
        return None

    if intent == UPDATE:
        if not slots.get("field"): return "field"
        if not slots.get("value"): return "value"
        return None

    if intent == ISSUE:
        if not slots.get("details"): return "details"
        return None

    return None

# =========================
# Textos (cortos, coherentes y con final)
# =========================
GREET_TXT = L("¡Hola! ¿En qué puedo ayudarte?|¡Buenas! ¿Qué necesitás resolver?|Hola 👋 ¿Compras, pagos, acceso o seguimiento?")
GREET_FOLLOW = L("Si me decís el tema, avanzamos rápido.|Contame qué querés hacer y te indico el siguiente paso.")
THANKS_TXT = L("Perfecto. ¿Necesitás algo más?|Genial, gracias. ¿Vemos algo más?")
AMBIG_TXT = L("¿Podés ampliar en una línea qué necesitás?|¿Me das un poco más de contexto?")

ASK_TXT = {
    "issue":  L("¿Es por contraseña, código o bloqueo?"),
    "account": L("¿Qué correo/usuario usás para ingresar?"),
    "case":   L("¿Es cobro no reconocido, duplicado o reembolso?"),
    "amount": L("¿Me confirmás el monto y la moneda (USD/GS)?"),
    "item":   L("¿Qué producto buscás (remera, jeans, zapatillas, mochila, etc.)?"),
    "refine": L("Perfecto. ¿Qué exactamente (remeras, jeans, buzos, zapatillas, mochilas)?"),
    "size":   L("¿Qué talle/número necesitás?"),
    "budget": L("¿Tenés un presupuesto aproximado?"),
    "ref":    L("¿Tenés un número de caso o referencia?"),
    "field":  L("¿Qué dato querés actualizar (correo, teléfono, dirección o nombre)?"),
    "value":  L("¿Cuál es el valor nuevo?"),
    "details": L("Entendido. ¿Qué error te aparece o qué paso estabas haciendo?"),
}

def finalize(intent: str, st: State) -> str:
    ref = ticket(st)

    if intent == LOGIN:
        issue = st.slots.get("issue")
        acc = st.slots.get("account")
        if issue == "contraseña":
            return f"Listo. Recuperación iniciada para {acc}. Ref: {ref}."
        if issue == "código":
            return f"Listo. Reenvío de código solicitado para {acc}. Ref: {ref}."
        if issue == "bloqueo":
            return f"Listo. Solicitud de desbloqueo registrada para {acc}. Ref: {ref}."
        return f"Listo. Caso de acceso registrado. Ref: {ref}."

    if intent == PAYMENT:
        label = st.slots.get("case", "pago").replace("_", " ")
        amt = st.slots.get("amount")
        extra = f" por {amt}" if amt else ""
        return f"Listo. Caso registrado ({label}{extra}). Ref: {ref}."

    if intent == PURCHASE:
        it = st.slots.get("item", "compra")
        sz = st.slots.get("size")
        bd = st.slots.get("budget")
        extra = ""
        if sz: extra += f", {sz}"
        if bd: extra += f", {bd}"
        return f"Listo. Solicitud registrada ({it}{extra}). Ref: {ref}."

    if intent == STATUS:
        status = random.choice(["en revisión", "pendiente", "resuelto"])
        return f"Listo. El estado figura como “{status}”. Ref: {ref}."

    if intent == UPDATE:
        field = st.slots.get("field", "dato")
        return f"Listo. Cambio solicitado ({field}) registrado. Ref: {ref}."

    if intent == ISSUE:
        return f"Listo. Incidente registrado. Ref: {ref}."

    return f"Listo. Solicitud registrada. Ref: {ref}."

def respond(platform: str, user: str, text: str) -> str:
    key = thread_id(platform, user)
    st = CONV.get(key) or State(user=user)
    st.last_seen = time.time()
    st.user = user or st.user

    tn = norm(text)
    intent = classify(tn, st)

    # Si veníamos esperando algo, intent ya quedó fijo por classify() (por _expect)
    st.intent = intent if intent not in [THANKS] else (st.intent or GENERAL)

    # update slots + limpia expect si ya vino
    if st.intent in [PURCHASE, PAYMENT, LOGIN, STATUS, UPDATE, ISSUE]:
        got = extract(st.intent, tn)
        st.slots.update(got)
        if st.slots.get("_expect") and got.get(st.slots["_expect"]):
            st.slots.pop("_expect", None)

    # greeting/thanks/ambig rápido
    if intent == GREET:
        out = random.choice(GREET_TXT)
        if random.random() < 0.6: out += " " + random.choice(GREET_FOLLOW)
        CONV[key] = st; clamp_memory(CONV); return out

    if intent == THANKS:
        out = random.choice(THANKS_TXT)
        CONV[key] = st; clamp_memory(CONV); return out

    if intent == AMBIG:
        out = random.choice(AMBIG_TXT)
        CONV[key] = st; clamp_memory(CONV); return out

    # decidir qué falta
    miss = next_missing(st.intent or GENERAL, st.slots)

    if miss:
        # marca “qué esperamos” para mantener coherencia
        st.slots["_expect"] = miss
        if miss == "budget": st.slots["_asked_budget"] = "1"
        out = random.choice(ASK_TXT.get(miss, ASK_TXT["details"]))
        CONV[key] = st; clamp_memory(CONV); return out

    # si no falta nada => FINALIZA
    out = finalize(st.intent or GENERAL, st)
    # limpia expect para que futuras consultas puedan arrancar otra cosa
    st.slots.pop("_expect", None)
    CONV[key] = st; clamp_memory(CONV)
    return out

# =========================
# Random inbound coherente (continúa conversaciones)
# =========================
def synth_answer(st: State) -> str:
    ex = st.slots.get("_expect")
    if st.intent == LOGIN and ex == "issue":
        return random.choice(["Olvidé mi contraseña", "No me llega el código", "Cuenta bloqueada"])
    if st.intent == LOGIN and ex == "account":
        return random.choice(["usuario@email.com", "mi correo es usuario@email.com"])
    if st.intent == PAYMENT and ex == "case":
        return random.choice(["Es un cobro no reconocido", "Me cobraron dos veces", "Quiero reembolso"])
    if st.intent == PAYMENT and ex == "amount":
        return random.choice(["25 USD", "80.000 GS", "50 USD"])
    if st.intent == PURCHASE and ex in ["item", "refine"]:
        return random.choice(["remeras", "jeans", "buzos", "zapatillas", "mochilas"])
    if st.intent == PURCHASE and ex == "size":
        return random.choice(["Talle M", "Talle L", "Número 42"])
    if st.intent == PURCHASE and ex == "budget":
        return random.choice(["50 USD", "100 USD", "200.000 GS"])
    if st.intent == STATUS and ex == "ref":
        return random.choice(["48219", "93012", "55107"])
    if st.intent == UPDATE and ex == "field":
        return random.choice(["Correo", "Teléfono", "Dirección"])
    if st.intent == UPDATE and ex == "value":
        return random.choice(["nuevo@email.com", "0981 123 456"])
    if st.intent == ISSUE and ex == "details":
        return random.choice(["Me aparece error 403", "Se queda cargando y no avanza", "Se cierra sola al abrir"])
    return random.choice(SEEDS)

def gen_inbound(platform_hint: Optional[str] = None) -> Tuple[str, str, str]:
    platform = platform_hint if platform_hint in PLATFORMS else random.choice(PLATFORMS)

    # 55%: continuar una conversación existente (más sentido)
    existing = [k for k in CONV.keys() if k.startswith(platform + ":")]
    if existing and random.random() < 0.55:
        k = random.choice(existing)
        st = CONV.get(k)
        if st:
            return platform, st.user, synth_answer(st)

    return platform, random.choice(USERS), random.choice(SEEDS)

# =========================
# ROUTES
# =========================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/messages")
def api_messages():
    return jsonify({"messages": MESSAGES})

@app.route("/api/generate")
def api_generate():
    ph = request.args.get("platform")
    platform, user, text = gen_inbound(ph)
    t = thread_id(platform, user)

    inbound = mk_msg(platform, "user", user, text, t)
    out = respond(platform, user, text)
    system = mk_msg(platform, "system", AUTO_USER, out, t, reply_to=inbound["id"])

    MESSAGES.extend([inbound, system])
    clamp_memory(CONV)
    return jsonify({"generated": [inbound, system]})

@app.route("/api/send", methods=["POST"])
def api_send():
    d = request.get_json(silent=True) or {}
    raw = (d.get("platform") or d.get("app") or d.get("channel") or "whatsapp").lower()
    platform = raw if raw in PLATFORMS else "whatsapp"

    user = (d.get("user_name") or d.get("user") or d.get("sender") or "Usuario").strip() or "Usuario"
    text = (d.get("message") or d.get("text") or d.get("content") or "").strip()

    t = thread_id(platform, user)

    inbound = mk_msg(platform, "user", user, text, t)
    out = respond(platform, user, text)
    system = mk_msg(platform, "system", AUTO_USER, out, t, reply_to=inbound["id"])

    MESSAGES.extend([inbound, system])
    clamp_memory(CONV)
    return jsonify({"messages": [inbound, system]})

@app.route("/api/clear", methods=["POST"])
def api_clear():
    global SEQ
    MESSAGES.clear()
    CONV.clear()
    SEQ = 0
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
