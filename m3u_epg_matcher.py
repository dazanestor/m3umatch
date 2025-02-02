import os
import json
import time
import threading
import requests
import gzip
import xml.etree.ElementTree as ET
import logging
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for

# Configuración del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

data_dir = "./data"
config_dir = "./config"
config_file = os.path.join(config_dir, "config.json")
os.makedirs(data_dir, exist_ok=True)
os.makedirs(config_dir, exist_ok=True)

# Crear config.json si no existe
def ensure_config_exists():
    if not os.path.exists(config_file):
        with open(config_file, "w", encoding="utf-8") as file:
            json.dump([], file)

# Cargar configuración desde archivo JSON
def load_config():
    ensure_config_exists()
    with open(config_file, "r", encoding="utf-8") as file:
        return json.load(file)

# Guardar configuración en archivo JSON
def save_config():
    with open(config_file, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)

config = load_config()


def download_file(url, file_path):
    """ Descarga un archivo desde una URL con manejo de errores y logging """
    try:
        response = requests.get(url, stream=True, timeout=20)
        response.raise_for_status()
        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(1024):
                file.write(chunk)
        logging.info(f"Descarga exitosa: {url}")
        return True
    except requests.RequestException as e:
        logging.error(f"Error descargando {url}: {e}")
        return False


def process_lists():
    """ Descarga y procesa todas las listas cada 24h """
    while True:
        for item in config:
            m3u_url = item["m3u"]
            epg_url = item["epg"]
            list_name = item["name"]
            
            m3u_path = os.path.join(data_dir, f"{list_name}.m3u")
            epg_path = os.path.join(data_dir, f"{list_name}.xml.gz")
            output_path = os.path.join(data_dir, f"{list_name}_matched.m3u")
            
            logging.info(f"Procesando lista: {list_name}")
            success_m3u = download_file(m3u_url, m3u_path)
            success_epg = download_file(epg_url, epg_path)
            
            if success_m3u and success_epg:
                logging.info(f"Lista {list_name} procesada correctamente.")
            else:
                logging.warning(f"Falló la descarga de {list_name}. Revise las URLs.")
        
        logging.info("Esperando 24 horas para la siguiente actualización.")
        time.sleep(86400)  # Esperar 24 horas


def start_processing_thread():
    thread = threading.Thread(target=process_lists, daemon=True)
    thread.start()


@app.route("/add", methods=["POST"])
def add_list():
    """ Agrega una nueva lista para procesar desde la web """
    name = request.form.get("name")
    m3u = request.form.get("m3u")
    epg = request.form.get("epg")
    
    if name and m3u and epg:
        config.append({"name": name, "m3u": m3u, "epg": epg})
        save_config()
        return redirect(url_for('index'))
    return "Error: Datos inválidos", 400


@app.route("/update_list", methods=["POST"])
def update_list():
    """ Actualiza una lista existente """
    data = request.json
    for item in config:
        if item["name"] == data["name"]:
            item["m3u"] = data["m3u"]
            item["epg"] = data["epg"]
            save_config()
            return jsonify({"message": "Lista actualizada correctamente"})
    return jsonify({"error": "Lista no encontrada"}), 404


@app.route("/files/<filename>")
def get_file(filename):
    """ Permite descargar los archivos generados """
    return send_from_directory(data_dir, filename)


if __name__ == "__main__":
    ensure_config_exists()
    start_processing_thread()
    app.run(host="0.0.0.0", port=5000, threaded=True)
