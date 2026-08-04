import requests

try:
    response = requests.post('http://localhost:8000/api/v1/planning/friday-rush', json={'simulation_mode': False})
    print('Status:', response.status_code)
    if response.status_code == 200:
        print('Response:', response.json())
    else:
        print('Error:', response.text)
except Exception as e:
    print('Connection error:', e)