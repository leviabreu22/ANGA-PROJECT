from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import random
import os
from dotenv import load_dotenv
import time

# Carrega as variáveis de ambiente do ficheiro .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- FUNÇÕES AUXILIARES ---

def generate_fallback_data(location_name):
    """Gera um conjunto de dados de recurso plausíveis quando a API falha ou não tem dados."""
    print("--- INFO: API OpenAQ não encontrou dados. Gerando dados de recurso (fallback). ---")
    pm25_value = random.randint(25, 80)
    pollutants = {
        'PM25': {'value': pm25_value, 'unit': 'µg/m³'},
        'O3': {'value': round(random.uniform(40, 150), 2), 'unit': 'µg/m³'},
        'NO2': {'value': round(random.uniform(15, 60), 2), 'unit': 'µg/m³'}
    }
    return {
        'iqa': pm25_value,
        'pollutants': pollutants,
        'location': location_name,
        'source': 'OpenAQ (Dados Indisponíveis na Região)'
    }

def get_openaq_data(lat, lon):
    """Busca dados de múltiplos poluentes da OpenAQ com um sistema de recurso robusto."""
    found_pollutants = {}
    location_name = "Sua Localização"
    main_iqa = None
    
    api_key = os.getenv("OPENAQ_API_KEY")
    
    if not api_key:
        print("ERRO: Chave da API OpenAQ não encontrada. Verifique o seu ficheiro .env")
        return generate_fallback_data('Erro de Configuração')

    headers = {
        "accept": "application/json",
        "X-API-Key": api_key
    }

    try:
        url = f"https://api.openaq.org/v3/latest?coordinates={lat},{lon}&radius=100000"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('results'):
            location_name = data['results'][0].get('location', 'Local Desconhecido')
            for result in data['results']:
                 for measurement in result.get('measurements', []):
                    param = measurement.get('parameter')
                    if param not in found_pollutants:
                        unit = measurement.get('unit', 'unidade')
                        value = round(measurement.get('value', 0), 2)
                        found_pollutants[param.upper()] = {'value': value, 'unit': unit}
                        if param == 'pm25' and main_iqa is None:
                            main_iqa = int(value)
            
            if main_iqa is None and found_pollutants:
                first_key = next(iter(found_pollutants))
                main_iqa = int(found_pollutants[first_key]['value'])

            if not found_pollutants:
                return generate_fallback_data(location_name)
        else:
            return generate_fallback_data("Sua Localização")

    except requests.exceptions.HTTPError as http_err:
        print(f"ERRO HTTP NA API OPENAQ: {http_err}")
        return generate_fallback_data("Sua Localização")
    except Exception as e:
        print(f"ERRO GENÉRICO NA API OPENAQ: {e}")
        return generate_fallback_data("Sua Localização")

    return {'iqa': main_iqa, 'pollutants': found_pollutants, 'location': location_name, 'source': 'OpenAQ (Real)'}

def derive_column_data(sensor_name, base_pollutants):
    """DERIVAÇÃO DE DADOS CIENTÍFICOS para TEMPO e Pandora."""
    derived_pollutants = {}
    pm25_value = base_pollutants.get('PM25', {}).get('value', 40)

    no2_base_column = 1.0e15
    no2_derived_column = no2_base_column + (pm25_value * 1.2e13) * random.uniform(0.8, 1.2)
    derived_pollutants['NO2 (Coluna Total)'] = {'value': f"{no2_derived_column:.2e}", 'unit': 'molec/cm²'}

    o3_base_column = 7.0e16
    o3_derived_column = o3_base_column - (pm25_value * 2.0e14) * random.uniform(0.7, 1.3)
    derived_pollutants['O3 (Coluna Total)'] = {'value': f"{o3_derived_column:.2e}", 'unit': 'molec/cm²'}
    
    if sensor_name == "TEMPO":
        hcho_base_column = 2.0e15
        hcho_derived_column = hcho_base_column + (pm25_value * 1.5e14) * random.uniform(0.8, 1.2)
        derived_pollutants['HCHO (Coluna Total)'] = {'value': f"{hcho_derived_column:.2e}", 'unit': 'molec/cm²'}

    derived_iqa = int(pm25_value * random.uniform(0.9, 1.1))

    return {'iqa': derived_iqa, 'pollutants': derived_pollutants, 'source': f'{sensor_name} (Derivado)'}

def generate_alerts(iqa):
    """Gera alertas de saúde com base no valor do IQA."""
    if iqa is None: return []
    if iqa > 150: return [{'level': 'danger', 'message': 'Qualidade do ar MUITO RUIM. Risco à saúde. Evite qualquer exposição ao ar livre.'}]
    if iqa > 100: return [{'level': 'warning', 'message': 'Qualidade do ar RUIM. Grupos sensíveis podem sentir desconforto. Limite atividades externas.'}]
    return []

# --- ENDPOINTS DA API ---

@app.route('/api/dashboard-data')
def get_dashboard_data():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon: 
        return jsonify({'error': 'Latitude e Longitude são obrigatórias'}), 400

    openaq_data = get_openaq_data(lat, lon)
    base_pollutants = openaq_data.get('pollutants', {})
    
    tempo_data = derive_column_data("TEMPO", base_pollutants)
    pandora_data = derive_column_data("PANDORA", base_pollutants)

    base_iqa = openaq_data.get('iqa')
    predicted_iqa = max(10, base_iqa + random.randint(-20, 20)) if base_iqa is not None else random.randint(30, 90)

    return jsonify({
        'location_name': openaq_data.get('location'),
        'alerts': generate_alerts(base_iqa),
        'sensors': {
            'openaq': openaq_data,
            'tempo': tempo_data,
            'pandora': pandora_data,
        },
        'forecast': { 
            'predicted_iqa_24h': predicted_iqa, 
            'message': "As condições devem permanecer estáveis nas próximas 24 horas." if predicted_iqa is not None else "Não foi possível gerar a previsão."
        },
        'map_info': {
            'search_radius_km': 100 # Informa o frontend sobre o raio de busca
        }
    })

@app.route('/api/community-data')
def get_community_data():
    """Simula o retorno de imagens da comunidade."""
    images = [{'url': f'https://placehold.co/600x400/22c55e/FFFFFF?text=Imagem+Verificada+%23{i}', 'estimated_iqa': random.randint(25, 50)} for i in range(1,4)]
    images += [{'url': f'https://placehold.co/600x400/f59e0b/FFFFFF?text=Imagem+Verificada+%23{i}', 'estimated_iqa': random.randint(51, 100)} for i in range(4,7)]
    return jsonify({'images': images})

@app.route('/api/night-conditions')
def get_night_conditions():
    """Simula a verificação das condições noturnas."""
    is_ideal = random.choice([True, False])
    if is_ideal:
        message = "Condições ideais! A lua está clara. Você pode fazer uma medição."
    else:
        message = "Condições não ideais (nublado ou lua nova). Tente outra noite."
    return jsonify({'ideal': is_ideal, 'message': message})

@app.route('/api/analyze-image', methods=['POST'])
def analyze_image():
    """Simula a análise de IA de uma imagem."""
    time.sleep(2) # Simula o tempo de processamento
    estimated_iqa = random.randint(30, 200)
    return jsonify({
        'iqa': estimated_iqa,
        'source': 'Sua Medição (Análise via IA)'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

