"""
Data handler for caching and managing Metro API data.
"""


class DataHandler:
    """
    Handles caching and fetching of Metro API data.
    """
    
    def __init__(self, metro_api):
        """
        Initialize the DataHandler with a MetroAPI instance.
        
        Args:
            metro_api: MetroAPI instance to fetch data from.
        """
        self.metro_api = metro_api
        self._lines_cache = None
        self._stations_cache = {}  # Dictionary to store stations by LineCode
        self._predictions_cache = {}  # Dictionary to store predictions by station_id
    
    def fetch_lines(self):
        """
        Fetch lines from the Metro API and cache the result.
        
        Returns:
            DataFrame: Lines data from the API.
        """
        self._lines_cache = self.metro_api.get_lines()
        return self._lines_cache
    
    def get_cached_lines(self):
        """
        Get cached lines data.
        
        Returns:
            DataFrame or None: Cached lines data, or None if not yet fetched.
        """
        return self._lines_cache
    
    def fetch_stations(self, LineCode):
        """
        Fetch stations for a specific line from the Metro API and cache the result.
        
        Args:
            LineCode: String representing the line code (e.g., 'RD', 'BL', 'YL', 'OR', 'GR', 'SV').
            
        Returns:
            DataFrame: Stations data for the specified line from the API.
        """
        self._stations_cache[LineCode] = self.metro_api.get_stations(LineCode)
        return self._stations_cache[LineCode]
    
    def fetch_predictions(self, station_id):
        """
        Fetch predictions for a specific station from the Metro API and cache the result.
        
        Args:
            station_id: String representing the station code (e.g., 'C01').
            
        Returns:
            DataFrame: Predictions data for the specified station from the API.
        """
        self._predictions_cache[station_id] = self.metro_api.station_arrivals(station_id)
        return self._predictions_cache[station_id]
    
    def get_cached_stations(self, LineCode):
        """
        Get cached stations data for a specific line.
        Auto-fetches if not in cache.
        
        Args:
            LineCode: String representing the line code (e.g., 'RD', 'BL', 'YL', 'OR', 'GR', 'SV').
            
        Returns:
            DataFrame or None: Cached stations data for the specified line, or None if not yet fetched.
        """
        cached = self._stations_cache.get(LineCode)
        if cached is None:
            return self.fetch_stations(LineCode)
        return cached
    
    def get_cached_predictions(self, station_id):
        """
        Get cached predictions data for a specific station.
        Auto-fetches if not in cache.
        
        Args:
            station_id: String representing the station code (e.g., 'C01').
            
        Returns:
            DataFrame or None: Cached predictions data for the specified station, or None if not yet fetched.
        """
        cached = self._predictions_cache.get(station_id)
        if cached is None:
            return self.fetch_predictions(station_id)
        return cached

    def get_predictions_cache(self, station_id):
        """
        Get cached predictions data for a specific station without fetching.
        """
        return self._predictions_cache.get(station_id)
    
    def refresh(self):
        """
        Re-fetch all cached data from the API and update caches.
        This refreshes lines, all currently cached stations, and all currently cached predictions.
        """
        # Refresh lines
        self.fetch_lines()
        
        # Refresh all cached stations
        cached_line_codes = list(self._stations_cache.keys())
        for line_code in cached_line_codes:
            self.fetch_stations(line_code)
        
        # Refresh all cached predictions
        cached_station_ids = list(self._predictions_cache.keys())
        for station_id in cached_station_ids:
            self.fetch_predictions(station_id)
