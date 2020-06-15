from backend_code.cell_mapper import CellMapper
from backend_code.item_table import ItemTable

class DataFile:
    def __init__(self, file_path):
        self.file_path=file_path
        self.sheets=[]
        pass

class Project:
    def __init__(self, sparql_endpoint, name="Untitled"):
        self._data_files={}
        self._yaml_files={}
        self._wikifier_files={}
        self.sparql_endpoint=sparql_endpoint
        self.name=name
        self.associations=[]
    
    def add_data_file(self, file_path):
        pass

    def add_yaml_file(self, file_path):
        pass

    def add_wikifier_file(self, file_path):
        pass
    
    def associate(self, yaml_file, data_file, sheet=None):
        pass

    def run_project(self):
        pass

    def run_file(self, file):
        pass

    def run_sheet(self, file, sheet):
        pass

    def json_to_kgtk(self, json):
        pass

    @staticmethod
    def load_from_database(project_id):
        pass


