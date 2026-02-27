import os

def get_app_version():
    """Reads the application version from the VERSION file in the project root."""
    try:
        paths_to_check = [
            'VERSION',
            '../VERSION',
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'VERSION'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'VERSION'),
            '/app/VERSION'
        ]
        
        for p in paths_to_check:
            if os.path.exists(p):
                with open(p, 'r') as f:
                    return f.read().strip()
                    
        return "Unknown"
    except OSError as e:
        print(f"Error reading version: {e}")
        return "Unknown"
