import os
from pathlib import Path
import logging
from etk.wikidata import serialize_change_record
from app_config import DEFAULT_SPARQL_ENDPOINT
#IMPORTANT: the import from models must happen before the other backend_code imports because of flask circular imports
from backend_code.models import YamlObject 
from backend_code.item_table import ItemTable
from backend_code.t2wml_handler import generate_download_file
from backend_code.wikify_handler import process_wikified_output_file
from backend_code.spreadsheets.utilities import get_first_sheet_name

def run_t2wml(data_file_path: str, wikified_output_path: str, t2wml_spec: str, output_directory: str,
              sheet_name: str = None,
              sparql_endpoint: str = DEFAULT_SPARQL_ENDPOINT, debug=False):
    
    try:
        if not sheet_name:
            sheet_name = get_first_sheet_name(data_file_path)
        file_name = Path(data_file_path).name
        try:
            file_extension = file_name.split(".")[-1]
        except:
            logging.error("Data file has no extension")
            return
        new_file_path = str(Path.cwd() / 'temporary_files' / file_name)
        #os.makedirs(str(Path.cwd() / 'temporary_files'), exist_ok=True)
    except KeyError as e:
        logging.error("Invalid sheet name:"+str(e))
        return
    except Exception as e:
        logging.error("Invalid data file"+str(e))
        return

    try:
        item_table = ItemTable()
        process_wikified_output_file(wikified_output_path, item_table, new_file_path, sheet_name)
    except Exception as e:
        print(e)
        logging.error("Invalid Wikfied Output File")
        return

    try:
        yc = YamlObject(t2wml_spec, item_table, new_file_path, sheet_name, sparql_endpoint)
    except Exception as e:
        logging.error("Invalid YAML File")
        return

    filetype = "ttl"
    response = generate_download_file(yc, filetype)
    result_directory = '.'.join(file_name.split(".")[:-1])

    output_path = Path()
    if file_extension == "csv":
        output_path = Path(output_directory) / result_directory
    elif file_extension == "xls" or file_extension == "xlsx":
        output_path = Path(output_directory) / result_directory / sheet_name

    Path.mkdir(output_path, parents=True, exist_ok=True)

    with open(str(output_path / "results.ttl"), "w") as fp:
        fp.write(response["data"])

    with open(str(output_path / "changes.tsv"), "w") as fp:
        serialize_change_record(fp)

    os.remove(new_file_path)