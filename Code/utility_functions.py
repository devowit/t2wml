from typing import Union
from SPARQLWrapper import SPARQLWrapper, JSON
import string
import pyexcel
import os
import re
import json
import pickle
from time import time
from uuid import uuid4
from typing import Sequence
from google.oauth2 import id_token
from google.auth.transport import requests
from pathlib import Path
from oslo_concurrency import lockutils
from Code.property_type_map import property_type_map


def get_column_letter(n: int) -> str:
	"""
	This function converts the column index to column letter
	1 to A,
	5 to E, etc
	:param n:
	:return:
	"""
	string = ""
	while n > 0:
		n, remainder = divmod(n - 1, 26)
		string = chr(65 + remainder) + string
	return string


def get_excel_column_index(column: str) -> int:
	"""
	This function converts an excel column to its respective column index as used by pyexcel package.
	viz. 'A' to 0
	'AZ' to 51
	:param column:
	:return: column index of type int
	"""
	index = 0
	column = column.upper()
	column = column[::-1]
	for i in range(len(column)):
		index += ((ord(column[i]) % 65 + 1)*(26**i))
	return index-1


def get_excel_row_index(row: Union[str, int]) -> int:
	"""
	This function converts an excel row to its respective row index as used by pyexcel package.
	viz. '5' to 1
	10 to 9
	:param row:
	:return: row index of type int
	"""
	return int(row)-1


def get_actual_cell_index(cell_index: tuple) -> str:
	"""
	This function converts the cell notation used by pyexcel package to the cell notation used by excel
	Eg: (0,5) to A6
	:param cell_index: (col, row)
	:return:
	"""
	col = get_column_letter(int(cell_index[0])+1)
	row = str(int(cell_index[1]) + 1)
	return col+row


def get_property_type(wikidata_property: str, sparql_endpoint: str) -> str:
	"""
	This functions queries the wikidata to find out the type of a wikidata property
	:param wikidata_property:
	:param sparql_endpoint:
	:return:
	"""
	try:
		type = property_type_map[wikidata_property]
	except KeyError:
		query = """SELECT ?type WHERE {
			wd:"""+wikidata_property+""" rdf:type wikibase:Property ;
			wikibase:propertyType ?type .  
		}"""
		sparql = SPARQLWrapper(sparql_endpoint)
		sparql.setQuery(query)
		sparql.setReturnFormat(JSON)
		results = sparql.query().convert()
		try:
			type = results["results"]["bindings"][0]["type"]["value"].split("#")[1]
		except IndexError:
			type = "Property Not Found"
	return type


def excel_to_json(file_path: str, sheet_name: str = None) -> str:
	"""
	This function reads the excel file and converts it to JSON
	:param file_path:
	:param sheet_name:
	:return:
	"""
	sheet_data = {'columnDefs': [{'headerName': "", 'field': "^", 'pinned': "left"}], 'rowData': []}
	column_index_map = {}
	result = dict()
	if not sheet_name:
		result['sheetNames'] = list()
		book_dict = pyexcel.get_book_dict(file_name=file_path)
		for sheet in book_dict.keys():
			result['sheetNames'].append(sheet)
		sheet_name = result['sheetNames'][0]
		sheet = book_dict[sheet_name]
	else:
		result["sheetNames"] = None
		sheet = pyexcel.get_sheet(sheet_name=sheet_name, file_name=file_path)
	result["currentSheetName"] = sheet_name
	for i in range(len(sheet[0])):
		column = get_column_letter(i+1)
		column_index_map[i+1] = column
		sheet_data['columnDefs'].append({'headerName': column_index_map[i + 1], 'field': column_index_map[i + 1]})
	for row in range(len(sheet)):
		r = {'^': str(row + 1)}
		for col in range(len(sheet[row])):
			r[column_index_map[col+1]] = str(sheet[row][col]).strip()
		sheet_data['rowData'].append(r)

	result['sheetData'] = sheet_data
	return result


def read_file(file_path: str) -> str:
	"""
	This function returns the content of a file
	:param file_path:
	:return:
	"""
	with open(file_path, "r") as f:
		data = f.read()
	return data


def write_file(filepath: str, data: str) -> None:
	"""
	This function writes data to a file which is saved at the specified filepath
	:param filepath:
	:param data:
	:return:
	"""
	with open(filepath, "w") as f:
		f.write(data)
		f.close()


def check_special_characters(text: str) -> bool:
	"""
	This funtion checks if the text is made up of only special characters
	:param text:
	:return:
	"""
	return all(char in string.punctuation for char in str(text))


def check_if_empty(text: str) -> bool:
	"""
	This function checks if the text is empty or has only special characters
	:param text:
	:return:
	"""
	if text is None or str(text).strip() == "" or check_special_characters(text):
		return True
	return False


def translate_precision_to_integer(precision: str) -> int:
	"""
	This function translates the precision value to indexes used by wikidata
	:param precision:
	:return:
	"""
	if isinstance(precision, int):
		return precision
	precision_map = {
		"gigayear": 0,
		"gigayears": 0,
		"100 megayears": 1,
		"100 megayear": 1,
		"10 megayears": 2,
		"10 megayear": 2,
		"megayears": 3,
		"megayear": 3,
		"100 kiloyears": 4,
		"100 kiloyear": 4,
		"10 kiloyears": 5,
		"10 kiloyear": 5,
		"millennium": 6,
		"century": 7,
		"10 years": 8,
		"10 year": 8,
		"years": 9,
		"year": 9,
		"months": 10,
		"month": 10,
		"days": 11,
		"day": 11,
		"hours": 12,
		"hour": 12,
		"minutes": 13,
		"minute": 13,
		"seconds": 14,
		"second": 14
	}
	return precision_map[precision.lower()]


def delete_file(filepath: str) -> None:
	"""
	This function delets a file at the filepath
	:param filepath:
	:return:
	"""
	os.remove(filepath)


def split_cell(cell: str) -> Sequence[int]:
	"""
	This function parses excel cell indices to column and row indices supported by pyexcel
	For eg: A4 to 0, 3
	B5 to 1, 4
	:param cell:
	:return:
	"""
	x = re.search("[0-9]+", cell)
	row_span = x.span()
	col = cell[:row_span[0]]
	row = cell[row_span[0]:]
	return get_excel_column_index(col), get_excel_row_index(row)


def parse_cell_range(cell_range: str) -> Sequence[tuple]:
	"""
	This function parses the cell range and returns the row and column indices supported by pyexcel
	For eg: A4:B5 to (0, 3), (1, 4)
	:param cell_range:
	:return:
	"""
	cells = cell_range.split(":")
	start_cell = split_cell(cells[0])
	end_cell = split_cell(cells[1])
	return start_cell, end_cell


def natural_sort_key(s):
	"""
	This function generates the key for the natural sorting algorithm
	:param s:
	:return:
	"""
	_nsre = re.compile('([0-9]+)')
	return [int(text) if text.isdigit() else text.lower() for text in re.split(_nsre, s)]


def generate_id() -> str:
	"""
	This function generate unique ids
	:return:
	"""
	return uuid4().hex


def add_login_source_in_user_id(user_id, login_source):
	if login_source == "Google":
		return "G" + user_id


def verify_google_login(tn: str):
	error = None
	try:
		client_id = '859571913012-79n4clvbq11q8tifboltfqdvttlh74vr.apps.googleusercontent.com'
		request = requests.Request()
		user_info = id_token.verify_oauth2_token(tn, request, client_id)

		if user_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
			error = 'Wrong issuer'
			user_info = None

	except ValueError as e:
		user_info = None
		error = str(e)

	return user_info, error


def create_directory(upload_directory: str, uid: str, pid: str = None, ptitle: str = None):
	if uid and pid:
		Path(Path(upload_directory) / uid / pid / "df").mkdir(parents=True, exist_ok=True)
		Path(Path(upload_directory) / uid / pid / "wf").mkdir(parents=True, exist_ok=True)
		Path(Path(upload_directory) / uid / pid / "yf").mkdir(parents=True, exist_ok=True)
		with open(Path(upload_directory) / uid / pid / "project_config.json", "w") as file:
			project_config = {
								"pid": pid,
								"ptitle": ptitle,
								"cdate": int(time() * 1000),
								"mdate": int(time() * 1000),
								"currentDataFile": None,
								"currentSheetName": None,
								"dataFileMapping": dict(),
								"yamlMapping": dict(),
								"wikifierRegionMapping": dict()
							}
			json.dump(project_config, file, indent=3)
	elif uid:
		Path(Path(upload_directory) / uid).mkdir(parents=True, exist_ok=True)


def get_project_details(user_dir):
	projects = list()
	for project_dir in user_dir.iterdir():
		if project_dir.is_dir():
			with open(project_dir / "project_config.json", "r") as file:
				project_config = json.load(file)
				project_detail = dict()
				project_detail["pid"] = project_config["pid"]
				project_detail["ptitle"] = project_config["ptitle"]
				project_detail["cdate"] = project_config["cdate"]
				project_detail["mdate"] = project_config["mdate"]
				projects.append(project_detail)
	return projects


# def update_project_meta(uid: str, pid: str, project_meta: dict):
# 	@lockutils.synchronized('save_project_meta', fair=True, external=True, lock_path=str(Path.cwd() / "config" / uid / pid))
# 	def save_project_meta():
# 		file_path = str(Path.cwd() / "config"/ "uploads" / uid / pid / "project_config.json")
# 		with open(file_path) as json_data:
# 			data = json.load(json_data)
# 			for k in project_meta.keys():
# 				if k == "dataFileMapping" or k == "wikfierRegionMapping":
# 					data[k].update(project_meta[k])
# 				else:
# 					data[k] = project_meta[k]
# 		with open(file_path, 'w') as project_config:
# 			json.dump(data, project_config, indent=3)
#
# 	save_project_meta()


def get_region_mapping(uid, pid, project):
	file_name = project.get_wikifier_region_filname()
	region_file_path = Path.cwd() / "config" / "uploads" / uid / pid / "wf" / file_name
	region_file_path.touch(exist_ok=True)
	with open(region_file_path) as json_data:
		try:
			region_map = json.load(json_data)
		except json.decoder.JSONDecodeError:
			region_map = None
	return region_map, file_name


def update_wikifier_region_file(uid, pid, region_filename, region_qnodes):
	file_path = str(Path.cwd() / "config" / "uploads" / uid / pid / "wf" / region_filename)

	@lockutils.synchronized('update_wikifier_region_config', fair=True, external=True, lock_path=str(Path.cwd() / "config" / uid / pid / "wf"))
	def update_wikifier_region_config():
		with open(file_path, 'w') as wikifier_region_config:
			json.dump(region_qnodes, wikifier_region_config, indent=3)

	update_wikifier_region_config()


def deserialize_wikifier_config(uid, pid, region_filename):
	file_path = str(Path.cwd() / "config" / "uploads" / uid / pid / "wf" / region_filename)
	print(file_path)
	with open(file_path, 'r') as wikifier_region_config:
		wikifier_config = json.load(wikifier_region_config)
	return wikifier_config


def get_project_config_path(uid, pid):
	return str(Path.cwd() / "config" / "uploads" / uid / pid / "project_config.json")


def save_yaml_config(yaml_config_file_path, yaml_config):
	with open(yaml_config_file_path, 'wb') as config_file:
		pickle.dump(yaml_config, config_file)


def load_yaml_config(yaml_config_file_path):
	with open(yaml_config_file_path, 'rb') as config_file:
		yaml_config = pickle.load(config_file)
	return yaml_config
