import os
import json
import time
import threading
import requests
import gzip
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

data_dir = "./data"
config_file = "./config.json"
os.makedirs(data_dir, exist_ok=True)

# Cargar configuración desde archivo JSON
def load_config():
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as file:
            return json.load(file)
    return []

# Guardar configuración en archivo JSON
def save_config():
    with open(config_file, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)

config = load_config()


def download_file(url, file_path):
    """ Descarga un archivo desde una URL """
    try:
        response = requests.get(url, stream=True, timeout=20)
        response.raise_for_status()
        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(1024):
                file.write(chunk)
        return True
    except requests.RequestException:
        return False


def match_epg(m3u_path, epg_path, output_path):
    """ Matchea el EPG con la lista M3U """
    try:
        with gzip.open(epg_path, 'rt', encoding='utf-8') as file:
            epg_content = file.read()
        root = ET.fromstring(epg_content)
        
        epg_channels = {}
        for channel in root.findall("channel"):
            channel_id = channel.get("id")
            display_name = channel.find("display-name").text if channel.find("display-name") is not None else ""
            if channel_id and display_name:
                epg_channels[display_name.lower()] = channel_id

        with open(m3u_path, "r", encoding="utf-8") as file:
            m3u_content = file.readlines()
        
        new_m3u = ["#EXTM3U\n"]
        
        for line in m3u_content:
            if line.startswith("#EXTINF"):
                name = line.split(",")[-1].strip()
                epg_id = epg_channels.get(name.lower(), "")
                epg_tag = f' tvg-id="{epg_id}"' if epg_id else ""
                new_m3u.append(line.replace("#EXTINF:-1", f"#EXTINF:-1{epg_tag}"))
            else:
                new_m3u.append(line)
        
        with open(output_path, "w", encoding="utf-8") as file:
            file.writelines(new_m3u)
    except Exception as e:
        print(f"Error procesando {m3u_path}: {e}")


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
            
            if download_file(m3u_url, m3u_path) and download_file(epg_url, epg_path):
                match_epg(m3u_path, epg_path, output_path)
        
        time.sleep(86400)  # Esperar 24 horas


def start_processing_thread():
    thread = threading.Thread(target=process_lists, daemon=True)
    thread.start()


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


@app.route("/files/<filename>")
def get_file(filename):
    """ Permite descargar los archivos generados """
    return send_from_directory(data_dir, filename)


if __name__ == "__main__":
    start_processing_thread()
    app.run(host="0.0.0.0", port=5000, threaded=True)
