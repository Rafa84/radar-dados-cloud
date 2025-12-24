import feedparser
import google.generativeai as genai
import requests
import json
import os
from google.cloud import firestore

# --- CONFIGURAÇÃO (Variáveis de Ambiente) ---
RSS_URL = os.getenv('RSS_URL', 'https://medium.com/feed/tag/data-engineering')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Validação de variáveis obrigatórias
if not all([GEMINI_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("Variáveis de ambiente obrigatórias não configuradas")

# Configurações de IA e Banco
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')
db = firestore.Client()

def send_telegram(message):
    """
    Envia mensagem formatada para o Telegram.
    
    Args:
        message (str): Texto da mensagem em Markdown
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("✅ Mensagem enviada para o Telegram!")
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")

def fetch_and_summarize(request=None):
    """
    Função principal: busca artigos, verifica duplicatas, 
    gera resumo com IA e envia para Telegram.
    
    Args:
        request: Objeto HTTP request (obrigatório para Cloud Functions)
        
    Returns:
        JSON com status da operação
    """
    print("--- 1. Buscando artigos no Medium... ---")
    feed = feedparser.parse(RSS_URL)
    
    if not feed.entries:
        return json.dumps({"status": "Nenhum artigo encontrado"})

    # Itera sobre os 5 primeiros posts para achar um inédito
    artigo_novo = None
    
    for entry in feed.entries[:5]:
        link = entry.link
        
        # Verificação de duplicata no Firestore
        docs = db.collection('historico').where('link', '==', link).stream()
        
        if not list(docs):
            artigo_novo = entry
            print(f"✅ ACHADO NOVO: {entry.title}")
            break
        else:
            print(f"⏭️ PULEI (JÁ ENVIADO): {entry.title}")
    
    if not artigo_novo:
        print("Tudo repetido por hoje.")
        return json.dumps({"status": "Sem novidades"})

    # Processamento do artigo novo
    title = artigo_novo.title
    link = artigo_novo.link
    
    print("--- 2. Gerando resumo com IA... ---")
    prompt = f"""
    Aja como um Engenheiro de Dados Senior e sarcástico.
    Resuma para newsletter (PT-BR) em 2 frases.
    Artigo: {title}
    Link: {link}
    """
    
    try:
        response = model.generate_content(prompt)
        resumo = response.text
        
        # Envia para Telegram
        msg = f"🚨 *RADAR DADOS* 🚨\n\n{resumo}\n\n🔗 [Ler Original]({link})"
        send_telegram(msg)
        
        # Persiste no Firestore
        db.collection('historico').add({
            'titulo': title,
            'link': link,
            'data_envio': firestore.SERVER_TIMESTAMP
        })
        print("💾 Salvo no Firestore!")
        
        return json.dumps({"status": "Processado com sucesso"})
        
    except Exception as e:
        error_msg = f"Erro no processamento: {e}"
        print(f"❌ {error_msg}")
        return json.dumps({"status": "Erro", "detalhes": str(e)})