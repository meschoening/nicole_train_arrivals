import requests
import pandas as pd


class MetroAPI:
    """
    A class to interact with Metro transit data.
    """
    
    def __init__(self, api_key):
        """
        Initialize the MetroAPI object.
        """
        self.api_key = api_key
        self.base_url = "https://api.wmata.com/Rail.svc/json"
        self.predictions_url = "https://api.wmata.com/StationPrediction.svc/json"
    
    def get_lines(self):
        """
        Get all metro lines.
        
        Returns:
            pandas DataFrame containing metro lines data.
        """
        url = f"{self.base_url}/jLines"
        headers = {
            "api_key": self.api_key
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        return pd.DataFrame(data['Lines'])
    
    def get_stations(self, LineCode):
        """
        Get all metro stations for a specific line.
        
        Args:
            LineCode: String representing the line code (e.g., 'RD', 'BL', 'YL', 'OR', 'GR', 'SV').
        
        Returns:
            pandas DataFrame containing metro stations data.
        """
        url = f"{self.base_url}/jStations"
        headers = {
            "api_key": self.api_key
        }
        params = {
            "LineCode": LineCode
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        return pd.DataFrame(data['Stations'])
    
    def station_arrivals(self, station_id):
        """
        Get upcoming arrivals for a specific station.
        
        Args:
            station_id: String representing the station code (e.g., 'C01').
            
        Returns:
            pandas DataFrame containing upcoming arrivals data.
        """
        url = f"{self.predictions_url}/GetPrediction/{station_id}"
        headers = {
            "api_key": self.api_key
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        return pd.DataFrame(data['Trains'])

