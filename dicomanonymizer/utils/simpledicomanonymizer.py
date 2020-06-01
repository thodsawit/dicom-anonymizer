import re
import pydicom
import sys
import hashlib
from os.path import dirname, join

from random import randint

from .dicomfields import *


encodings = dict()
#structure: {element_keyword: {original_value: encrypted_value}}


dictionary = {}

# Default anonymization functions


def encrypt_string(hash_string):
    sha_signature = hashlib.sha256(hash_string.encode()).hexdigest()
    return sha_signature


def replaceElementUID(element):
    """
    if element.value not in dictionary:
        new_chars = [str(randint(0, 9)) if char.isalnum() else char for char in element.value]
        dictionary[element.value] = ''.join(new_chars)
    element.value = dictionary.get(element.value)
    """
    #modified implementation --> encrypt using sha256 standard
    encrypted_value = encrypt_string(element.value)

    #add to encodings dictionary --> will be written to csv later
    element_keyword = element.keyword
    if element_keyword not in encodings:
        encodings[element_keyword] = dict()
    encodings[element_keyword][element.value] = encrypted_value

    element.value = encrypted_value


def replaceElementDate(element):
    element.value = '00010101'


def replaceElementDateTime(element):
    element.value = '00010101010101.000000+0000'


def replaceElement(element):
    if element.VR == 'DA':
        replaceElementDate(element)
    elif element.VR == 'TM':
        element.value = '000000.00'
    elif element.VR in ('LO', 'SH', 'PN', 'CS'):
        element.value = 'Anonymized'
    elif element.VR == 'UI':
        replaceElementUID(element)
    elif element.VR == 'UL':
        pass
    elif element.VR == 'IS':
        element.value = '0'
    elif element.VR == 'SS':
        element.value = 0
    elif element.VR == 'SQ':
        for subDataset in element.value:
            for subElement in subDataset.elements():
                replaceElement(subElement)
    elif element.VR == 'DT':
        replaceElementDateTime(element)
    else:
        raise NotImplementedError('Not anonymized. VR {} not yet implemented.'.format(element.VR))


def replace(dataset, tag):
    """
    D - replace with a non-zero length value that may be a dummy value and consistent with the
    VR
    """
    element = dataset.get(tag)
    if element is not None:
        replaceElement(element)


def emptyElement(element):
    if (element.VR in ('SH', 'PN', 'UI', 'LO', 'CS')):
        element.value = ''
    elif element.VR == 'DA':
        replaceElementDate(element)
    elif element.VR == 'TM':
        element.value = '000000.00'
    elif element.VR == 'UL':
        element.value = 0
    elif element.VR == 'SQ':
        for subDataset in element.value:
            for subElement in subDataset.elements():
                emptyElement(subElement)
    else:
        raise NotImplementedError('Not anonymized. VR {} not yet implemented.'.format(element.VR))


def empty(dataset, tag):
    """
    Z - replace with a zero length value, or a non-zero length value that may be a dummy value and
    consistent with the VR
    """
    element = dataset.get(tag)
    if element is not None:
        emptyElement(element)


def deleteElement(dataset, element):
    if element.VR == 'DA':
        replaceElementDate(element)
    elif element.VR == 'SQ':
        for subDataset in element.value:
            for subElement in subDataset.elements():
                deleteElement(subDataset, subElement)
    else:
        del dataset[element.tag]


def delete(dataset, tag):
    """X - remove"""
    def rangeCallback(dataset, dataElement):
        if dataElement.tag.group & tag[2] == tag[0] and dataElement.tag.element & tag[3] == tag[1]:
            deleteElement(dataset, dataElement)

    if (len(tag) > 2):  # Tag ranges
        dataset.walk(rangeCallback)
    else:  # Individual Tags
        element = dataset.get(tag)
        if element is not None:
            deleteElement(dataset, element)  # element.tag is not the same type as tag.


def keep(dataset, tag):
    """K - keep (unchanged for non-sequence attributes, cleaned for sequences)"""
    pass


def clean(dataset, tag):
    """
    C - clean, that is replace with values of similar meaning known not to contain identifying
    information and consistent with the VR
    """
    if dataset.get(tag) is not None:
        raise NotImplementedError('Tag not anonymized. Not yet implemented.')


def replaceUID(dataset, tag):
    """
    U - replace with a non-zero length UID that is internally consistent within a set of Instances
    Lazy solution : Replace with empty string
    """
    element = dataset.get(tag)
    if element is not None:
        replaceElementUID(element)


def emptyOrReplace(dataset, tag):
    """Z/D - Z unless D is required to maintain IOD conformance (Type 2 versus Type 1)"""
    replace(dataset, tag)


def deleteOrEmpty(dataset, tag):
    """X/Z - X unless Z is required to maintain IOD conformance (Type 3 versus Type 2)"""
    empty(dataset, tag)


def deleteOrReplace(dataset, tag):
    """X/D - X unless D is required to maintain IOD conformance (Type 3 versus Type 1)"""
    replace(dataset, tag)


def deleteOrEmptyOrReplace(dataset, tag):
    """
    X/Z/D - X unless Z or D is required to maintain IOD conformance (Type 3 versus Type 2 versus
    Type 1)
    """
    replace(dataset, tag)


def deleteOrEmptyOrReplaceUID(dataset, tag):
    """
    X/Z/U* - X unless Z or replacement of contained instance UIDs (U) is required to maintain IOD
    conformance (Type 3 versus Type 2 versus Type 1 sequences containing UID references)
    """
    element = dataset.get(tag)
    if element is not None:
        if element.VR == 'UI':
            replaceElementUID(element)
        else:
            emptyElement(element)

# Generation functions

actionsMapNameFunctions = {
    "replace": replace,
    "empty": empty,
    "delete": delete,
    "replaceUID": replaceUID,
    "emptyOrReplace": emptyOrReplace,
    "deleteOrEmpty": deleteOrEmpty,
    "deleteOrReplace": deleteOrReplace,
    "deleteOrEmptyOrReplace": deleteOrEmptyOrReplace,
    "deleteOrEmptyOrReplaceUID": deleteOrEmptyOrReplaceUID,
    "keep": keep
}

def generateActions(tagList, action):
    """Generate a dictionnary using list values as tag and assign the same value to all
    :type tagList: list
    """
    finalAction = action
    if not callable(action):
        finalAction = actionsMapNameFunctions[action] if action in actionsMapNameFunctions else keep
    return {tag: finalAction for tag in tagList}


def initializeActions():
    """Initialize anonymization actions with DICOM standard values
    """
    anonymizationActions = generateActions(D_TAGS, replace)
    anonymizationActions.update(generateActions(Z_TAGS, empty))
    anonymizationActions.update(generateActions(X_TAGS, delete))
    anonymizationActions.update(generateActions(U_TAGS, replaceUID))
    anonymizationActions.update(generateActions(Z_D_TAGS, emptyOrReplace))
    anonymizationActions.update(generateActions(X_Z_TAGS, deleteOrEmpty))
    anonymizationActions.update(generateActions(X_D_TAGS, deleteOrReplace))
    anonymizationActions.update(generateActions(X_Z_D_TAGS, deleteOrEmptyOrReplace))
    anonymizationActions.update(generateActions(X_Z_U_STAR_TAGS, deleteOrEmptyOrReplaceUID))
    return anonymizationActions

def anonymizeDICOMFile(inFile, outFile, dictionary = ''):
    """Anonymize a DICOM file by modyfying personal tags

    Conforms to DICOM standard except for customer specificities.

    :param inFile: File path or file-like object to read from
    :param outFile: File path or file-like object to write to
    :param dictionary: add more tag's actions
    """
    currentAnonymizationActions = initializeActions()

    if dictionary != '':
        currentAnonymizationActions.update(dictionary)

    dataset = pydicom.dcmread(inFile)

    for tag, action in currentAnonymizationActions.items():
        action(dataset, tag)

    # X - Private tags = (0xgggg, oxeeee) where 0xgggg is odd
    dataset.remove_private_tags()


    #black out burned-in patient information
    #use UltrasoundRegion dataElements to specify areas to be blacked out
    dataset.decompress()
    # read image data
    img = dataset.pixel_array
    h = img.shape[0]
    w = img.shape[1]

    try:
        ultrasound_regions = dataset.SequenceOfUltrasoundRegions
    except:
        ultrasound_regions = []

    if len(ultrasound_regions) == 0:
        #default --> pad top 10% of image with black banner
        pad_space = int(0.1 * h)
        img[:pad_space] = 0
    else:
        #turn all area outside ultrasound pane into black color
        x0_union = w
        x1_union = 0
        y0_union = h
        y1_union = 0
        #find single box that covers all regions
        for region in ultrasound_regions:
            x0_union = min(x0_union, region.RegionLocationMinX0)
            x1_union = max(x1_union, region.RegionLocationMaxX1)
            y0_union = min(y0_union, region.RegionLocationMinY0)
            y1_union = max(y1_union, region.RegionLocationMaxY1)
        x0 = max(x0_union, 0)
        x1 = min(x1_union, w)
        y0 = max(y0_union, 0)
        y1 = min(y1_union, h)
        img[:, :x0] = 0
        img[:, x1:] = 0
        img[:y0] = 0
        img[y1:] = 0

    dataset.PixelData = img.tobytes()



    # Store modified image
    # set output filename as encrypted SOPInstanceUID
    out_filename = encrypt_string(dataset.SOPInstanceUID)
    out_filename = out_filename[:int(len(out_filename)/2)]+".dcm"
    outdir = dirname(outFile)
    dataset.save_as(join(outdir, out_filename))
