import os
from pathlib import Path
import pandas as pd
from driver import run_t2wml

def get_sheet_names(file_path):
    """
    This function returns the first sheet name of the excel file
    :param file_path:
    :return:
    """
    print(file_path)
    file_extension=Path(file_path).suffix
    is_csv = True if file_extension.lower() == ".csv" else False
    if is_csv:
        return [Path(file_path).name]
    xl = pd.ExcelFile(file_path)
    return xl.sheet_names

def run_same_yaml_on_multiple_datasheets(yaml_file, wikifier_file, data_file_folder, project_name, output_directory):    
    for filename in os.listdir(data_file_folder):
        total_results=""
        data_file_path=os.path.join(data_file_folder, filename)
        print(data_file_path)
        sheet_names=get_sheet_names(data_file_path)
        for sheet_name in sheet_names:
            run_t2wml(data_file_path, wikifier_file, yaml_file, output_directory, sheet_name, filetype="tsv", project_name=project_name)

if __name__=="__main__":
    yaml_file=#"path/to/yaml"
    wikifier_file=#"/path/to/wikifier"
    data_file_folder= #"path/to/folder/containing/datafiles"
    project_name="MyBatchProject"
    output_folder=#path/to/save/files
    run_same_yaml_on_multiple_datasheets(yaml_file, wikifier_file, data_file_folder, project_name, output_folder)
    