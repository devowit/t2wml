import re
import json
from pathlib import Path
import requests
from typing import List
from backend_code.item_table import ItemTable
from backend_code import t2wml_exceptions as T2WMLExceptions
from backend_code.spreadsheets.utilities import create_temporary_csv_file
import pandas as pd
import uuid

def wikifier(item_table: ItemTable, region: str, excel_file_path: str, sheet_name: str, flag, context,
             sparql_endpoint) -> dict:
    """
    This function processes the calls to the wikifier service and adds the output to the ItemTable object
    :param sparql_endpoint:
    :param item_table:
    :param region:
    :param excel_file_path:
    :param sheet_name:
    :return:
    """
    if not item_table:
        item_table = ItemTable()
    cell_qnode_map = wikify_region(region, excel_file_path, sheet_name)
    if not context:
        context = '__NO_CONTEXT__'
    cell_qnode_map['context'] = context
    item_table.update_table(cell_qnode_map, excel_file_path, sheet_name, flag)
    # item_table.add_region(region, cell_qnode_map)
    return item_table.serialize_table(sparql_endpoint)

def wikify_region(region: str, excel_file_path: str, sheet_name: str = None):
    """
    This function parses the cell range, creates the temporary csv file and calls the wikifier service on that csv
    to get the cell qnode map. cell qnode map is then processed to omit non empty cells and is then returned.
    :param region:
    :param excel_file_path:
    :param sheet_name:
    :return:
    """
    file_path = create_temporary_csv_file(region, excel_file_path, sheet_name)
    cell_qnode_map = call_wikify_service(file_path, cell_range[0][0], cell_range[0][1])
    return cell_qnode_map

def call_wikify_service(csv_file_path: str, col_offset: int, row_offset: int):
    """
    This function calls the wikifier service and creates a cell to qnode dictionary based on the response
    cell to qnode dictionary = { 'A4': 'Q383', 'B5': 'Q6892' }
    :param csv_file_path:
    :param col_offset:
    :param row_offset:
    :return:
    """
    cell_qnode_map = dict()
    with open(csv_file_path, 'r') as f:
        files = {
            'file': ('', f),
            'format': (None, 'ISWC'),
            'type': (None, 'text/csv'),
            'header': (None, 'False')
        }
        response = requests.post('https://dsbox02.isi.edu:8888/wikifier/wikify', files=files)
    output = None
    if response.status_code == 200:
        data = response.content.decode("utf-8")
        data = json.loads(data)['data']
        data = [x.split(",") for x in data]
        output = pd.DataFrame(data, columns=["column", "row", "item"])
        for index in range(output.shape[0]):
            output.at[index, 'column'] = int(output.at[index, 'column']) + col_offset
            output.at[index, 'row'] = int(output.at[index, 'row']) + row_offset
    return output