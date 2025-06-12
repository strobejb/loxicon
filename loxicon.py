import os
import shutil
import argparse
import glob
import re
import datetime
import getpass
import requests

from requests.auth import HTTPBasicAuth
from xml.etree  import ElementTree as ET
from ftplib     import FTP, all_errors

from natsort    import natsorted
from mutablezip import MutableZipFile

ICON_LIBRARY = "IconLibrary.zip"

#def rndUUID():
#    import uuid
#    return ''.join(str(uuid.uuid4()).rsplit('-',1)).upper()

def loxUUID(idx):
    BASE = 0x10000000
    uuid = f'{int(idx)|BASE :08X}-00FF-0000-0000000000000000'
    return uuid

#
#   Add an SVG icon to the zipfile. zf should be opened in append mode
#
def add_icon_svg(zf, iconPath, iconName, force=False):

    iconZipDest = 'IconsFilled/'+iconName
    if iconZipDest in zf.namelist() and force is False:
        print('Skipping:  ', iconZipDest)
        return False
    else:
        print('Adding svg:', iconZipDest)
        zf.write(iconPath, iconZipDest)
        return True

#
#   Add an XML entry to describe the icon
#
def add_icon_xml(ixml, iconName, index, tags, line, filled, force=False):
    iconRoot = ixml.getroot()
    
    existing = iconRoot.find(f'Icon[@Id="{iconName}"]')

    if existing is not None and force is False:
        print(f'Skipping: {existing.attrib["Id"]}')
        return None

    newIcon = ET.Element('Icon', 
                            uuid   = str(loxUUID(index)),
                            Id     = iconName,
                            Tags   = ','.join(tags),
                            line   = str(line).lower(),
                            filled = str(filled).lower())
    
    print('Adding xml:', ET.tostring(newIcon, encoding='unicode'))
    iconRoot.append(newIcon)
    return True          





def add_icons_to_library(zf, iconList, tags=[], line=True, filled=True, force=False, languages=['']):

    libraryXMLNames = [f'IconLibrary{"_" if lang else ""}{lang}.xml' for lang in languages]

    #
    #   Add the icon resources
    #
    for icon in iconList:
        add_icon_svg(zf, icon['path'], icon['name'], force)

    #
    # parse each IconLibrary.XML / add icon entries
    #
    for ilxname in libraryXMLNames:
        print(f'Updating: {ilxname}')
        modified = False        

        with zf.open(ilxname, 'r') as ilf:
            xmlroot = ET.parse(ilf)       

            for icon in iconList:     
                if add_icon_xml(xmlroot, icon['name'], icon['index'], tags, line, filled, force):
                    modified = True

        # write the new version of the XML file
        if modified:
            
            xmldata = ET.tostring(xmlroot.getroot(), encoding='utf-8', method='xml')            
            zf.writestr(ilxname, xmldata)

    # update the library version
    if modified:
        print('Updating: version')
        today_date = datetime.datetime.now().strftime('%Y%m%d')
        zf.writestr('version', today_date)


#
#   Find the latest Loxone Config install location
#
def find_icon_library():
    progdata = os.getenv("ProgramData")
    
    if progdata:
        loxd = os.path.join(progdata, "Loxone")
        vers = natsorted(glob.glob('Loxone Config *', root_dir=loxd))
        if vers:
            path = os.path.join(loxd, vers[-1], ICON_LIBRARY)
            print(f'Found: {path}')            
            return path

    return None

def compile_svgs(iconspec):
    # capture an optional prefixed digit followed by the actual name
    # i.e. 123.name.svg  -> (123, name.svg)
    #      name      -> None, name
    rx = re.compile(r'^(?:(\d+)\.)?(.*)')

    files = []
    prefix = 'x-'

    for file in glob.glob(iconspec):
        name = os.path.basename(file)
        m = rx.match(name)
        i = m.group(1) if m.group(1) else len(files)+1

        if m.group(1):
            files.append(dict(index=int(i), 
                          name=prefix + m.group(2),
                          path=file
                    ))
    return files    

def upload_to_miniserver(miniserver, source, dest):

    print(f'Connecting to miniserver: {miniserver}')

    username = input('Username: ')
    password = getpass.getpass(prompt='Password: ')
        
    try:
        with FTP(miniserver, username, password) as ftp:
            print(ftp.getwelcome())
            name = os.path.basename(source)
            with open(source,'rb') as f:
                print(f'Uploading: {source} -> {dest}')
                r = ftp.storbinary(f'STOR {dest}', f)    # send the file
                print(r)

    except all_errors as e:
        print(f'Error: {e}')


    answer = input("Reboot Miniserver? [y/n]: ").lower()
    if answer == 'y' or answer == 'yes':
        uri = f'http://{miniserver}/dev/sys/reboot'
        r = requests.get(uri, auth=(username, password))
        print(r.text)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
                    prog='LoxIcon',
                    description='Update Loxone Icon Library with custom SVG icons')
    
    parser.add_argument('--icons',     type=str, default='*.svg', help='Path spec to the SVG icon to add')
    parser.add_argument('--library',   type=str, default = find_icon_library(), help='Path to IconLibrary.zip' )
    parser.add_argument('--languages', type=str, default=['ENG', 'DEU'], nargs='+', help='Languages to target')    
    parser.add_argument('--tags',      type=str, default=['custom'], nargs='+', help="Optional tags to apply to each icon")    
    parser.add_argument('--force',      default=False, action='store_true')
    parser.add_argument('--overwrite',  default=False, action="store_true")
    parser.add_argument('--miniserver', type=str, help='IP address of miniserver to upload IconLibrary.zip')

    #args = parser.parse_args(['--force'])    
    #args = parser.parse_args(['--miniserver', '192.168.1.25'])
    args = parser.parse_args()

    svglist = compile_svgs(args.icons)

    if not args.overwrite:
        # default to updating a copy in the current directory
        print(f'Saving copy: {ICON_LIBRARY}')
        shutil.copy(args.library, ICON_LIBRARY)
        original = args.library
        args.library = ICON_LIBRARY

    with MutableZipFile(args.library, mode='a') as zf:
        args.languages.insert(0, '')
        add_icons_to_library(zf, svglist, 
                             force=args.force, 
                             languages=args.languages,
                             tags=args.tags, 
                             line=True,
                             filled=True,
                             )

    if args.miniserver:
        upload_to_miniserver(args.miniserver, args.library, f'/sys/{ICON_LIBRARY}')

    if not args.overwrite:
        print(f'You should now copy IconLibrary.zip to: {original}\n'\
            '  and update the Miniserver. Both Loxone Config and the Miniserver should have the\n'\
            '  same copy of the library to ensure the custom icons are available in the app.')
    print('Done.')
