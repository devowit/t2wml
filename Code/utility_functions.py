from typing import Union
from SPARQLWrapper import SPARQLWrapper, JSON
import string
import pyexcel
import os
from Code.property_type_map import property_type_map


def get_column_letter(n):
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


def get_actual_cell_index(cell_index):
	col = get_column_letter(cell_index[0]+1)
	row = str(cell_index[1] + 1)
	return col+row


def get_property_type(wikidata_property: str) -> str:
	try:
		type = property_type_map[wikidata_property]
	except KeyError:
		query = """SELECT ?type WHERE {
			wd:"""+wikidata_property+""" rdf:type wikibase:Property ;
			wikibase:propertyType ?type .  
		}"""

		sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
		sparql.setQuery(query)
		sparql.setReturnFormat(JSON)
		results = sparql.query().convert()
		try:
			type = results["results"]["bindings"][0]["type"]["value"].split("#")[1]
		except IndexError:
			type = "Property Not Found"
	return type


def excel_to_json(file_path, sheet_name=None):
	book_dict = pyexcel.get_book_dict(file_name=file_path)
	sheet_data = {'columnDefs': [{'headerName': "", 'field': "^", 'pinned': "left"}], 'rowData': []}
	column_index_map = {}

	file_path = file_path.lower()
	is_first_excel = (False, True)[(file_path.endswith(".xls") or file_path.endswith(".xlsx")) and (sheet_name == None)]

	result = dict()
	if not sheet_name:
		result['sheetNames'] = list()
		for sheet in book_dict.keys():
			result['sheetNames'].append(sheet)
		sheet_name = result['sheetNames'][0]

	sheet = book_dict[sheet_name]
	for i in range(len(sheet[0])):
		column = get_column_letter(i+1)
		column_index_map[i+1] = column
		sheet_data['columnDefs'].append({'headerName': column_index_map[i + 1], 'field': column_index_map[i + 1]})
	for row in range(len(sheet)):
		r = {'^': str(row + 1)}
		for col in range(len(sheet[row])):
			r[column_index_map[col+1]] = str(sheet[row][col]).strip()
		sheet_data['rowData'].append(r)

	if is_first_excel:
		result['sheetData'] = dict()
		result['sheetData'][sheet_name] = sheet_data
		return result
	else:
		return sheet_data


def read_file(file_path):
	with open(file_path, "r") as f:
		return f.read()


def write_file(filepath, data):
	with open(filepath, "w") as f:
		f.write(data)
		f.close()


def check_special_characters(text) -> bool:
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


def delete_file(filepath):
	os.remove(filepath)
# def assign_qnodes_to_cells(excel_file: str, wikified_output: str, sheet_name: str = None) -> dict:
