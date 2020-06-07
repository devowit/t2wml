import csv
import json
import warnings
from io import StringIO
from types import CodeType
from pathlib import Path
from etk.wikidata.utils import parse_datetime_string
from SPARQLWrapper.SPARQLExceptions import QueryBadFormed

from backend_code.t2wml_exceptions import T2WMLException, make_frontend_err_dict
import backend_code.t2wml_exceptions as T2WMLExceptions
from backend_code.parsing.classes import ReturnClass
from backend_code.parsing.constants import char_dict
from backend_code.parsing.t2wml_parsing import iter_on_n_for_code
from backend_code.spreadsheets.conversions import to_excel

from backend_code.triple_generator import generate_triples
from backend_code.utility_functions import translate_precision_to_integer, get_property_type


def parse_time_for_dict(response, sparql_endpoint):
    if "property" in response:
        try:
            prop_type= get_property_type(response["property"], sparql_endpoint)
        except QueryBadFormed:
            raise T2WMLExceptions.InvalidT2WMLExpressionException("The value given for property is not a valid property:" +str(response["property"]))
        
        if prop_type=="Time":
            if "format" in response:
                with warnings.catch_warnings(record=True) as w: #use this line to make etk stop harassing us with "no lang features detected" warnings
                    try:
                        datetime_string, precision = parse_datetime_string(str(response["value"]),
                                                                            additional_formats=[
                                                                                response["format"]])
                    except ValueError:
                        raise T2WMLExceptions.InvalidT2WMLExpressionException("Attempting to parse datetime string that isn't a datetime:" + str(response["value"]))

                    if "precision" not in response:
                        response["precision"] = int(precision.value.__str__())
                    else:
                        response["precision"] = translate_precision_to_integer(response["precision"])
                    response["value"] = datetime_string



def get_template_statement(template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint):
    if item_parsed:
        template["item"]=item_parsed.value
        template["cell"]=to_excel(item_parsed.col, item_parsed.row)
    if value_parsed:
        template["value"]=value_parsed.value
    
    attributes={"qualifier": qualifiers_parsed, "reference": references_parsed}
    for attribute_name in attributes:
        attribute=attributes[attribute_name]
        if attribute:
            for attribute_dict in attribute:
                q_val=attribute_dict.pop("value", None) #deal with value last
                for key in attribute_dict:
                    if isinstance(attribute_dict[key], ReturnClass):
                        attribute_dict[key]=attribute_dict[key].value
                
                attribute_dict["value"]=q_val #add q_val back, then deal with it
                if q_val:
                    if isinstance(q_val, ReturnClass):
                        attribute_dict["value"]=q_val.value
                        attribute_dict["cell"]=to_excel(q_val.col, q_val.row)
                
                parse_time_for_dict(attribute_dict, sparql_endpoint)    

            template[attribute_name]=attribute

    parse_time_for_dict(template, sparql_endpoint)
    return template


def _evaluate_template_for_list_of_dicts(attributes, context):
    attributes_parsed=[]
    for attribute in attributes:
        new_dict=dict(attribute)
        for key in attribute:
            if isinstance(attribute[key], CodeType):
                q_parsed=iter_on_n_for_code(attribute[key], context)
                new_dict[key]=q_parsed
        attributes_parsed.append(new_dict)
    return attributes_parsed


def evaluate_template(template, context):
    item=template.get("item", None)
    value=template.get("value", None)
    qualifiers=template.get("qualifier", None)
    references=template.get("reference", None)

    item_parsed=value_parsed=qualifiers_parsed=references_parsed=None


    if item:
        item_parsed= iter_on_n_for_code(item, context)

    if value:
        value_parsed= iter_on_n_for_code(value, context)
    
    if qualifiers:
        qualifiers_parsed = _evaluate_template_for_list_of_dicts(qualifiers, context)
    
    if references:
        references_parsed = _evaluate_template_for_list_of_dicts(references, context)
        
    
    return item_parsed, value_parsed, qualifiers_parsed, references_parsed

    
    

def update_highlight_data(data, item_parsed, qualifiers_parsed, references_parsed):
    if item_parsed:
        item_cell=to_excel(item_parsed.col, item_parsed.row)
        if item_cell:
            data["item"].add(item_cell)
    
    
    attributes_parsed_dict= {'qualifierRegion': qualifiers_parsed, 'referenceRegion': references_parsed}
    for label, attributes_parsed in attributes_parsed_dict.items():
        if attributes_parsed:
            attribute_cells = set()
            for attribute in attributes_parsed:
                attribute_parsed=attribute.get("value", None)
                if attribute_parsed and isinstance(attribute_parsed, ReturnClass):
                    attribute_cell=to_excel(attribute_parsed.col, attribute_parsed.row)
                    if attribute_cell:
                        attribute_cells.add(attribute_cell)
            data[label] |= attribute_cells




def highlight_region(cell_mapper):
    sparql_endpoint=cell_mapper.sparql_endpoint
    if cell_mapper.use_cache:
        data=cell_mapper.cacher.get_highlight_region()
        if data:
            return data

    highlight_data = {"dataRegion": set(), "item": set(), "qualifierRegion": set(), 'referenceRegion': set(), 'error': dict()}
    statement_data=[]
    for col, row in cell_mapper.region:
        cell=to_excel(col-1, row-1)
        highlight_data["dataRegion"].add(cell)
        context={"t_var_row":row, "t_var_col":col}
        try:
            item_parsed, value_parsed, qualifiers_parsed, references_parsed= evaluate_template(cell_mapper.eval_template, context)
            update_highlight_data(highlight_data, item_parsed, qualifiers_parsed, references_parsed)

            if cell_mapper.use_cache:
                    statement=get_template_statement(cell_mapper.template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint)
                    if statement:
                        statement_data.append(
                            {'cell': cell, 
                            'statement': statement})
        except T2WMLException as exception:
            error = exception.error_dict
            highlight_data['error'][to_excel(col, row)] = error
    if highlight_data["error"]:
        raise T2WMLExceptions.InvalidT2WMLExpressionException(message=str(highlight_data["error"])) #TODO: return this properly, not as a str(dict)
    highlight_data['dataRegion'] = list(highlight_data['dataRegion'])
    highlight_data['item'] = list(highlight_data['item'])
    highlight_data['qualifierRegion'] = list(highlight_data['qualifierRegion'])
    highlight_data['referenceRegion'] = list(highlight_data['referenceRegion'])

    if cell_mapper.use_cache:
        cell_mapper.cacher.save(highlight_data, statement_data)
    return highlight_data


def resolve_cell(cell_mapper, col, row):
    sparql_endpoint=cell_mapper.sparql_endpoint
    context={"t_var_row":int(row), "t_var_col":char_dict[col]}
    try:
        item_parsed, value_parsed, qualifiers_parsed, references_parsed= evaluate_template(cell_mapper.eval_template, context)
        statement=get_template_statement(cell_mapper.template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint)
        if statement:
            data = {'statement': statement, 'error': None}
        else:
            data = {'statement': None, 'error': "Item doesn't exist"}
    except T2WMLException as exception:
        error = exception.error_dict
        data = {'error': error}
    return data



def generate_download_file(cell_mapper, filetype):
    if filetype in ["tsv", "kgtk"]:
        raise ValueError("Please use download_kgtk function to create tsv files for the kgtk format")
    if filetype not in ["json", "ttl"]:
        raise ValueError("Unsupported file type")

    sparql_endpoint=cell_mapper.sparql_endpoint
    response=dict()
    error=[]
    data=[]
    if cell_mapper.use_cache:
        data=cell_mapper.cacher.get_download()
    
    if not data:
        for col, row in cell_mapper.region:
            try:
                context={"t_var_row":row, "t_var_col":col}
                item_parsed, value_parsed, qualifiers_parsed, references_parsed= evaluate_template(cell_mapper.eval_template, context)
                statement=get_template_statement(cell_mapper.template, item_parsed, value_parsed, qualifiers_parsed, references_parsed, sparql_endpoint)
                if statement:
                    data.append(
                        {'cell': to_excel(col-1, row-1), 
                        'statement': statement})
            except T2WMLException as e:
                error.append({'cell': to_excel(col, row), 
                'error': str(e)})


    if filetype == 'json':
        response["data"] = json.dumps(data, indent=3)
        response["error"] = None if not error else error
        return response
    
    elif filetype == 'ttl':
        response["data"] = generate_triples("n/a", data, sparql_endpoint, created_by=cell_mapper.created_by)
        response["error"] = None if not error else error
        return response



def kgtk_add_property_type_specific_fields(property_dict, result_dict, sparql_endpoint):
    property_type= get_property_type(property_dict["property"], sparql_endpoint)
    
    #The only property that doesn't require value
    if property_type=="GlobeCoordinate": 
        '''
        node2;kgtk:latitude: for coordinates, the latitude
        node2;kgtk:longitude: for coordinates, the longitude
        '''
        result_dict["node2;kgtk:data_type"]="coordinate" #not defined for sure yet
        result_dict["node2;kgtk:latitude"]=property_dict["latitude"]
        result_dict["node2;kgtk:longitude"]=property_dict["longitude"]
        result_dict["node2;kgtk:precision"]=property_dict.get("precision", "")
        result_dict[" node2;kgtk:globe"]=property_dict.get("globe", "")

    else:
        value=property_dict["value"]

        if property_type=="Quantity":
            '''
            node2;kgtk:magnitude: for quantities, the number
            node2;kgtk:units_node: for quantities, the unit
            node2;kgtk:low_tolerance: for quantities, the lower bound of the value (cannot do it in T2WML yet)
            node2;kgtk:high_tolerance: for quantities, the upper bound of the value (cannot do it in T2WML yet)
            '''
            result_dict["node2;kgtk:data_type"]="quantity"
            result_dict["node2;kgtk:number"]= value
            result_dict["node2;kgtk:units_node"]= property_dict.get("unit", "")
            result_dict["node2;kgtk:low_tolerance"]= property_dict.get("lower-bound", "")
            result_dict["node2;kgtk:high_tolerance"]= property_dict.get("upper-bound", "")

        elif property_type=="Time":
            '''
            node2;kgtk:date_and_time: for dates, the ISO-formatted data
            node2;kgtk:precision: for dates, the precision, as an integer (need to verify this with KGTK folks, could be that we use human readable strings such as year, month
            node2;kgtk:calendar: for dates, the qnode of the calendar, if specified
            '''
            result_dict["node2;kgtk:data_type"]="date_and_times"
            result_dict["node2;kgtk:date_and_time"]=value
            result_dict["node2;kgtk:precision"]=property_dict.get("precision", "")
            result_dict["node2;kgtk:calendar"]=property_dict.get("calendar", "")



        elif property_type in ["String", "MonolingualText", "ExternalIdentifier"]:
            '''
            node2;kgtk:text: for text, the text without the language tag
            node2;kgtk:language: for text, the language tag
            '''
            result_dict["node2;kgtk:data_type"]="string"
            result_dict["node2;kgtk:text"]="\""+value+"\""
            result_dict["node2;kgtk:language"]=property_dict.get("lang", "")

        elif property_type in ["WikibaseItem", "WikibaseProperty"]:
            result_dict["node2;kgtk:data_type"]="symbol"
            "node2;kgtk:symbol: when node2 is another item, the item goes here"
            result_dict["node2;kgtk:symbol"]=value
        
        else:
            raise ValueError("Property type "+property_type+" is not currently supported")

def download_kgtk(cell_mapper, project_name, file_path, sheet_name):
    response=generate_download_file(cell_mapper, "json")
    data=json.loads(response["data"])
    file_name=Path(file_path).stem
    file_extension=Path(file_path).suffix

    if file_extension==".csv":
        sheet_name=""

    tsv_data=[]
    for entry in data:
        cell=entry["cell"]
        id = project_name + ";" + file_name + "." + sheet_name + file_extension + ";" + cell
        statement=entry["statement"]
        cell_result_dict=dict(id=id, node1=statement["item"], label=statement["property"])
        kgtk_add_property_type_specific_fields(statement, cell_result_dict, cell_mapper.sparql_endpoint)
        tsv_data.append(cell_result_dict)

        qualifiers=statement.get("qualifier", [])
        for qualifier in qualifiers:
            second_cell=qualifier.get("cell", "")
            q_id = project_name + ";" + file_name + "." + sheet_name + "." + file_extension + ";" + cell +";"+second_cell
            qualifier_result_dict=dict(id=q_id, node1=id, label=qualifier["property"])
            kgtk_add_property_type_specific_fields(qualifier, qualifier_result_dict, cell_mapper.sparql_endpoint)
            tsv_data.append(qualifier_result_dict)

        references = statement.get("reference", [])
        #todo: handle references


    string_stream= StringIO("", newline="")
    fieldnames=["id", "node1", "label","node2", "node2;kgtk:data_type",
                "node2;kgtk:number","node2;kgtk:low_tolerance","node2;kgtk:high_tolerance", "node2;kgtk:units_node",
                "node2;kgtk:date_and_time", "node2;kgtk:precision", "node2;kgtk:calendar",
                "node2;kgtk:truth", 
                "node2;kgtk:symbol",
                "node2;kgtk:latitude", "node2;kgtk:longitude",
                "node2;kgtk:text", "node2;kgtk:language", ]

    writer = csv.DictWriter(string_stream, fieldnames,
                            restval="", delimiter="\t", lineterminator="\n",
                            escapechar='', quotechar='',
                            dialect=csv.unix_dialect, quoting=csv.QUOTE_NONE)
    writer.writeheader()
    for entry in tsv_data:
        writer.writerow(entry)
    
    response["data"]=string_stream.getvalue()
    string_stream.close()

    return response