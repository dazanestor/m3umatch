import os
import json
import time
import threading
import requests
import gzip
import xml.etree.ElementTree as ET
import logging
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for
from werkzeug.utils import secure_filename

# Configuración del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

data_dir = "./data"
config_dir = "./config"
config_file = os.path.join(config_dir, "config.json")
app.config['UPLOAD_FOLDER'] = data_dir
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


@app.route("/")
def index():
    file_list = os.listdir(data_dir)
    files_html = "".join(f'<li><a href="/files/{file}">{file}</a></li>' for file in file_list)
    
    return f'''
    <html><body>
    <h2>Subir archivos</h2>
    <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <input type="submit" value="Subir">
    </form>
    <h2>Listas disponibles</h2>
    <ul>{files_html}</ul>
    </body></html>
    '''


@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('index'))
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return redirect(url_for('index'))


@app.route("/add", methods=["POST"])
def add_list():
    """ Agrega una nueva lista para procesar """
    data = request.json
    if "name" in data and "m3u" in data and "epg" in data:
        config.append(data)
        save_config()
        return jsonify({"message": "Lista añadida"}), 200
    return jsonify({"error": "Datos inválidos"}), 400


@app.route("/lists", methods=["GET"])
def get_lists():
    """ Retorna la configuración de listas """
    return jsonify(config)


@app.route("/update", methods=["POST"])
def update_now():
    """ Fuerza la actualización inmediata de listas """
    threading.Thread(target=process_lists).start()
    return jsonify({"message": "Actualización en proceso"}), 200


@app.route("/files/<filename>")
def get_file(filename):
    """ Permite descargar los archivos generados """
    return send_from_directory(data_dir, filename)


if __name__ == "__main__":
    ensure_config_exists()
    start_processing_thread()
    app.run(host="0.0.0.0", port=5000, threaded=True)
