from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
import copy
from app_config import db, DEFAULT_SPARQL_ENDPOINT, UPLOAD_FOLDER
from backend_code.item_table import ItemTable
from backend_code.t2wml_exceptions import T2WMLException
from backend_code.utility_functions import save_wikified_result
from backend_code.spreadsheets.utilities import excel_to_json, add_excel_file_to_bindings
from backend_code.spreadsheets.caching import load_file
from backend_code.handler import resolve_cell, highlight_region, process_wikified_output_file, update_bindings
from backend_code.yaml_parser import YAMLParser
from backend_code.bindings import bindings
from backend_code.region import Region

def generate_id() -> str:
    """
    This function generate unique ids
    :return:
    """
    return uuid4().hex

def base_upload_path(user_id, project_id):
    return Path(UPLOAD_FOLDER) / user_id / project_id

class User(db.Model):
    uid= db.Column(db.String(64), primary_key=True)
    given_name = db.Column(db.String(64))
    family_name = db.Column(db.String(64))
    email = db.Column(db.String(120), index=True)
    projects=db.relationship("Project", back_populates="user")
    picture = db.Column(db.String(120))
    #self.__locale = locale

    @property
    def name(self):
        return self.given_name + " " + self.family_name

    def __repr__(self):
        return '<User {} : {}>'.format(self.name, self.uid)

    @staticmethod
    def get_or_create(uid, given_name=None, family_name=None, email=None, *args, **kwargs):
        try:
            u=User.query.get(uid)
            if u is None:
                raise ValueError("user not found") 
            return u
        except:
            if email is None:
                raise ValueError("No user fields provided and user does not already exist")
        u=User(uid=uid, given_name=given_name, family_name=family_name, email=email)
        db.session.add(u)
        up_dir=Path(UPLOAD_FOLDER)/ uid
        up_dir.mkdir(parents=True, exist_ok=True)
        db.session.commit()  
        return u

    @property
    def json_dict(self):
        return {
            'email':self.email,
            'familyName':self.family_name,
            'givenName':self.given_name,
            'name':self.name,
            'picture':self.picture, 
            'projects':{} #this is always empty, as far as I can tell
        }
    
    def get_project_details(self):
        projects = list()
        for project in self.projects:
            project_detail = dict()
            project_detail["pid"] = project.id
            project_detail["ptitle"] = project.name
            project_detail["cdate"] = str(project.creation_date)
            project_detail["mdate"] = str(project.modification_date)
            projects.append(project_detail)
        return projects

class Project(db.Model):
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String(64), index=True)
    creation_date=db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    modification_date=db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    sparql_endpoint=db.Column(db.String(64), nullable=True, default=DEFAULT_SPARQL_ENDPOINT)

    user_id=db.Column(db.Integer, db.ForeignKey('user.uid'))
    user=db.relationship("User", back_populates="projects")

    projectfiles=db.relationship("ProjectFile", back_populates="project")
    current_file = db.relationship("ProjectFile",
                    primaryjoin="and_(Project.id==ProjectFile.project_id, "
                        "ProjectFile.current==True)",
                    back_populates="project",
                    uselist=False)

    def __repr__(self):
        return '<Project {}: {}>'.format(self.name, self.id)  
    
    @staticmethod
    def delete(pid):
        proj=Project.query.get(pid)
        db.session.delete(proj)
        db.session.commit()

    @staticmethod
    def create(user_id, title):
        pid=generate_id()
        p=Project(id=pid, name=title, user_id=user_id)
        db.session.add(p)
        Project.make_directories(user_id, pid)
        db.session.commit()
        return p
    
    @staticmethod
    def make_directories(uid, pid):
        """
        This function creates the project directory along with the project_config.json
        current_working_directory
                                |__config/
                                        |__uploads/
                                                |__<user_id>/
                                                            |__<project_id>/
                                                                        |__df/
                                                                        |__wf/
                                                                        |__yf/
                                                                        |__project_config.json
        :param upload_directory:
        :param uid:
        :param pid:
        :param ptitle:
        :return:
        """
        project_path=base_upload_path(uid, pid)
        Path(project_path/ "df").mkdir(parents=True, exist_ok=True)
        Path(project_path/ "wf").mkdir(parents=True, exist_ok=True)
        Path(project_path/ "yf").mkdir(parents=True, exist_ok=True)

    def get_current_file_and_sheet(self):
        try:
            current_file = self.current_file.id
            current_sheet = current_file.current_sheet_name
            return current_file, current_sheet
        except IndexError:
            return None, None
        
    def modify(self):
        self.modificationdate=datetime.utcnow()
        db.session.commit()
    
    @property
    def wikifier_folder_path(self):
        return str(base_upload_path(self.user_id, self.id) / "wf")
    
    @property
    def wikifier_output_filepath(self):
        return str(Path(self.wikifier_folder_path) / "other.csv")

    @property
    def serialized_wikifier_output_filepath(self):
        return str(Path(self.wikifier_folder_path) / "result.csv")
    
    def change_wikifier_file(self, file):
        file.save(self.wikifier_output_filepath)
        self.modify()

    def update_sparql_endpoint(self, endpoint):
        self.sparql_endpoint=endpoint
        self.modify()
    
    def update_project_title(self, title):
        self.name=title
        self.modify()

class ProjectFile(db.Model):
    id = db.Column(db.String, primary_key=True)
    filepath = db.Column(db.String(200), index=True)
    name = db.Column(db.String(64))

    current=db.Column(db.Boolean, default=False)

    project_id=db.Column(db.Integer, db.ForeignKey('project.id'))
    project=db.relationship("Project", back_populates="projectfiles")

    sheets=db.relationship("ProjectSheet", back_populates="project_file")
    current_sheet = db.relationship("ProjectSheet",
                    primaryjoin="and_(ProjectFile.id==ProjectSheet.file_id, "
                        "ProjectSheet.current==True)",
                    back_populates="project_file",
                    uselist=False)
    
    def __repr__(self):
        return '<ProjectFile {} {}>'.format(self.name, self.id)  

    @property
    def new_filename(self):
        return self.id + Path(self.name).suffix
    
    @property
    def current_sheet_name(self):
        if self.current_sheet:
            return self.current_sheet.name
        return None

    @property
    def sheet_names(self):
        if self.sheets:
            return [sheet.name for sheet in self.sheets]
        return None #also for all csvs
        
    @property
    def is_csv(self):
        file_extension=Path(self.filepath).suffix
        is_csv = True if file_extension.lower() == ".csv" else False
        return is_csv

    @staticmethod
    def create(file, uid, pid):
        pf_id=generate_id()
        file_extension=Path(file.filename).suffix
        new_filename=pf_id+file_extension
        file_path = str(base_upload_path(uid, pid)/ "df" / new_filename)
        file.save(file_path)
        pf=ProjectFile(id=pf_id, filepath=file_path, project_id=pid, name=file.filename)
        db.session.add(pf)
        db.session.commit()
        pf.init_sheets()
        #pf.modify()
        return pf
    
    def init_sheets(self):
        sheet_names=load_file(self.filepath)
        first=sheet_names[0]
        for sheet_name in sheet_names:
            pr = ProjectSheet(name=sheet_name, file_id=self.id, current=sheet_name==first)
            db.session.add(pr)
        db.session.commit()
    
    def change_sheet(self, sheet_name):
        newcurrsheet=ProjectSheet.query.filter_by(name=sheet_name, file_id=self.id).first()
        if newcurrsheet:
            newcurrsheet.set_as_current()
        else:
            raise ValueError("No such sheet")

    def modify(self):
        self.project.modify()
    
    def set_as_current(self):
        if self.project.current_file:
            self.project.current_file.current=False
        self.current=True
        self.modify()
    
    def tableData(self):
        data=excel_to_json(self.filepath, self.current_sheet_name)
        return {
            "filename":self.name,
            "isCSV":self.is_csv,
            "sheetNames": self.sheet_names,
            "currSheetName": self.current_sheet_name,
            "sheetData": data
        }

class ProjectSheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))

    current=db.Column(db.Boolean, default=False)

    file_id=db.Column(db.Integer, db.ForeignKey('project_file.id'))
    project_file=db.relationship("ProjectFile", back_populates="sheets")
    
    yaml_file=db.relationship("YamlFile", uselist=False, back_populates="sheet",
    primaryjoin="YamlFile.sheet_id==ProjectSheet.id")

    wiki_region_file=db.relationship("WikiRegionFile", uselist=False, back_populates="sheet",
    primaryjoin="WikiRegionFile.sheet_id==ProjectSheet.id")

    def __repr__(self):
        return '<Project sheet {}>'.format(self.id)  
    
    @staticmethod
    def create(name, file_id):
        ps=ProjectSheet(name=name, file_id=file_id)
        db.session.add(ps)
        db.session.commit()
        ps.modify()
        return ps
        
    def modify(self):
        self.project_file.modify()
    
    def set_as_current(self):
        if self.project_file.current_sheet:
            self.project_file.current_sheet.current=False
        self.current=True
        self.modify()

    @property
    def item_table(self):
        if self.wiki_region_file:
            return self.wiki_region_file.item_table
        else:
            return ItemTable(None)


class YamlObject:
    def __init__(self):
        self._region={'left': None, 'right': None, 'top': None, 'bottom': None, 
                        'skip_row': None, 'skip_column': None, 'skip_cell':None,
                        'region_object': None}
        self.template=None
        self.created_by='t2wml'
    
    def get_template_copy(self):
        return copy.deepcopy(self.template)
    
    @property
    def region(self):
        return self._region

    @region.setter
    def region(self, new_dict):
        for key in self._region:
            self._region[key]=new_dict[key]

    @staticmethod
    def create(yaml_filepath: str, item_table: ItemTable, data_file_path: str, sheet_name: str):
        """
        This function loads the YAML file data, parses different expressions and generates the statement
        :param yaml_filepath:
        :return:
        """
        yaml_parser = YAMLParser(yaml_filepath)
        update_bindings(item_table, None, data_file_path, sheet_name)
        region = yaml_parser.get_region(bindings)
        region['region_object'] = Region(region, item_table, data_file_path, sheet_name)
        template = yaml_parser.get_template()
        created_by = yaml_parser.get_created_by()
        yaml_configuration=YamlObject()
        yaml_configuration.region= region
        yaml_configuration.template= template
        yaml_configuration.created_by= created_by
        return yaml_configuration
    

class YamlFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sheet_id=db.Column(db.Integer, db.ForeignKey('project_sheet.id'))
    sheet=db.relationship("ProjectSheet", back_populates="yaml_file")
    
    @staticmethod
    def get_or_create(sheet, yaml_data):
        if sheet.yaml_file:
            yf = sheet.yaml_file
        else:
            yf=YamlFile(sheet_id=sheet.id)
            db.session.add(yf)
            db.session.commit()
        
        with open(yf.yaml_file_path, "w", newline='') as f:
            f.write(yaml_data)

        yf.sheet.modify()
        return yf
    
    @property
    def yaml_configuration(self):
        try:
            yc=self._yaml_configuration
            return yc
        except:
            self._yaml_configuration=YamlObject.create(self.yaml_file_path,
                        self.sheet.item_table, self.sheet.project_file.filepath, self.sheet.name)
            return self._yaml_configuration


    def highlight_region(self):
        return highlight_region(self.sheet.item_table, self.sheet.project_file.filepath, 
                            self.sheet.name, self.yaml_configuration.region, self.yaml_configuration.template, self.sheet.project_file.project.sparql_endpoint)

    def resolve_cell(self, column, row):
        return resolve_cell(self.sheet.item_table, 
                            self.sheet.project_file.filepath, 
                            self.sheet.name, 
                            self.yaml_configuration.region, 
                            self.yaml_configuration.template, 
                            column, row, 
                            self.sheet.project_file.project.sparql_endpoint)

    @staticmethod
    def get_handler(sheet):
        if sheet.yaml_file:
            try:
                return sheet.yaml_file.handle()
            except Exception as e:
                return None #TODO: can't return a better error here yet, it breaks the frontend
        return None
    @property
    def yaml_file_name(self): 
        return str(self.id) + ".yaml"
    
    @property
    def user_id(self):
        return self.sheet.project_file.project.user_id
    
    @property
    def project_id(self):
        return self.sheet.project_file.project_id

    @property
    def yaml_file_path(self):
        return str(base_upload_path(self.user_id, self.project_id)/ "yf" / self.yaml_file_name)

    
    def handle(self):
        item_table=self.sheet.item_table

        response=dict()
        with open(self.yaml_file_path, "r") as f:
            response["yamlFileContent"]= f.read()
        template = self.yaml_configuration.template
        region = self.yaml_configuration.region
        response['yamlRegions'] = highlight_region(item_table, self.sheet.project_file.filepath, self.sheet.name, region, template)
        
        return response





class WikiRegionFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sheet_id=db.Column(db.Integer, db.ForeignKey('project_sheet.id'))
    sheet=db.relationship("ProjectSheet", back_populates="wiki_region_file")
    
    @property
    def item_table(self):
        try:
            if self._item_table:
                return self._item_table
            raise ValueError("item table not yet initialized")
        except:
            region_map=None
            try:
                with open(self.region_file_path) as json_data:
                    region_map = json.load(json_data)
                    self._item_table = ItemTable(region_map)
                    return self._item_table
            except (AttributeError, FileNotFoundError, json.decoder.JSONDecodeError):
                return ItemTable(None)



    @property 
    def project(self):
        return self.sheet.project_file.project

    @property
    def project_id(self):
        return self.project.id
    
    @property
    def user_id(self):
        return self.project.user_id 

    @property
    def wikifier_folder_path(self):
        return self.project.wikifier_folder_path
    
    @property
    def wikifier_output_filepath(self):
        return self.project.wikifier_output_filepath

    @property
    def serialized_wikifier_output_filepath(self):
        return self.project.serialized_wikifier_output_filepath
        
    @property
    def region_file_name(self):
        return str(self.id)+".json"
    
    @property
    def region_file_path(self):
        return str(Path(self.wikifier_folder_path) / self.region_file_name)
    
    @property
    def sparql_endpoint(self):
        return self.sheet.project_file.project.sparql_endpoint

    @staticmethod
    def get_or_create(sheet):
        if sheet.wiki_region_file:
            return sheet.wiki_region_file
        w=WikiRegionFile(sheet_id=sheet.id)
        db.session.add(w)
        db.session.commit()
        sheet.modify()
        return w

    def handle(self):
        project_file=self.sheet.project_file
        item_table=self.item_table
        
        add_excel_file_to_bindings(self.sheet.project_file.filepath, self.sheet.name)
        
        if Path(self.wikifier_output_filepath).exists():
            process_wikified_output_file(self.wikifier_output_filepath, item_table, project_file.filepath, self.sheet.name)

        serialized_table=self.serialize_and_save(item_table)
        self.update_wikifier_region_file(item_table)
        return serialized_table

    def update_wikifier_region_file(self, item_table):
        with open(self.region_file_path, 'w') as wikifier_region_config:
            wikifier_region_config.write(item_table.to_json())
        self._item_table=None

    def serialize_and_save(self, item_table):
        from backend_code.utility_functions import save_wikified_result
        serialized_table = item_table.serialize_table(self.sparql_endpoint)
        save_wikified_result(serialized_table['rowData'], self.serialized_wikifier_output_filepath)
        return serialized_table
