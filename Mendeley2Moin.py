# -*- coding: utf-8 -*-
"""
    MoinMoin - Mendeley to Wiki actions
    
    @copyright: 2012 Rafael Funke
    @license: GNU GPL, see COPYING for details.
    
    Methods for output of content with header and/or footer based on CreateNewPage Action:
    CreateNewPage Action
    @copyright: 2007 by Oliver Siemoneit
    @license: GNU GPL, see COPYING for details.

"""

from MoinMoin import wikiutil
from MoinMoin.Page import Page
from MoinMoin.PageEditor import PageEditor
from MoinMoin.parser.text_moin_wiki import Parser as WikiParser
from MoinMoin.action import AttachFile
from pprint import pformat
from mendeley_client import MendeleyClient
from string import Template, join
from datetime import date
import re, os, traceback, oauth2

#name of page that this module uses for config, etc.
_wiki_base = 'Mendeley2Moin'

#called by MoinMoin; makes this plugin appear as "action" plugin in MoinMoin
def execute(pagename, request):
	return Mendeley2MoinActionHandler(pagename, request).handle_request()

#Class for API communication with mendeley.com
class MendeleyImporter:
	#parameters are OAuth keys
	def __init__(self, consumer_key, secret_key):
		self.mendeley = MendeleyClient(consumer_key, secret_key)
	
	#fetches URL for authenticating tokens
	def get_auth_url(self):
		self.mendeley.request_token = self.mendeley.mendeley.request_token()
		return(self.mendeley.mendeley.authorize(self.mendeley.request_token))
	
	#loads authenticated OAuth tokens
	def load_keys(self, api_keys_pkl_dir):
		#dirty hack
		tmp_cwd = os.getcwd()
		os.chdir(api_keys_pkl_dir)
		self.mendeley.load_keys()
		os.chdir(tmp_cwd)
	#dumps authenticated OAuth tokens to file
	def save_keys(self, api_keys_pkl_dir):
		#same dirty hack as before
		tmp_cwd = os.getcwd()
		os.chdir(api_keys_pkl_dir)
		self.mendeley.save_keys()
		os.chdir(tmp_cwd)
	
	#get dictionary with folder IDs and names
	def get_folders(self):
		return self.mendeley.folders()
	
	#get list of dictionarys with document details from given folder, or all documents if folder_id is 0
	def get_documents(self, folder_id):
		list_result = []
		#get document_ids for docs in given folder
		if folder_id == 0:
			#all documents
			fold = self.mendeley.library()
		else:
			fold = self.mendeley.folder_documents(folder_id)
		#get details for document_ids
		for doc in fold['document_ids']:
			doc_details = self.mendeley.document_details(doc)
			if not 'citation_key' in doc_details:
				#awkward, mendeley did not give citation_key
				#let's be creative and generate one
				doc_details['citation_key'] = ''
				if doc_details['authors']!=[]:
					doc_details['citation_key'] += doc_details['authors'][0]['surname']
				if 'year' in doc_details:
					doc_details['citation_key'] += doc_details['year']+'_'
				doc_details['citation_key'] += doc_details['id']
			list_result.append(doc_details)
		return list_result
	
	# parses serialized request token and the verifier that was given by user
	def set_verified_token(self, token_string, verifier):
		self.mendeley.request_token = oauth2.Token.from_string(token_string)
		self.mendeley.mendeley.authorize(self.mendeley.request_token)
		self.mendeley.request_token.set_verifier(verifier)
		self.mendeley.access_token = self.mendeley.mendeley.access_token(self.mendeley.request_token)

#The base plugin class. Handles interaction with user and generates output pages
class Mendeley2MoinActionHandler:
	#takes pagename and request, which are passed through to execute function by MoinMoin
	def __init__(self, pagename, request):
		self.pagename = pagename
		self.request = request
		#empty dict, will be filled with configuration later
		self.config = dict()
	
	#reads a wiki page containing the configuration and parses configuration
	def read_config(self, wiki_page_config):
		re_confline = re.compile('^\s*([a-zA-Z_-]+)\s*=\s*([^#]+)')
		raw = wiki_page_config.get_raw_body()
		for line in raw.splitlines():
			result = re_confline.match(line)
			if result != None:
				self.config[result.group(1)] = result.group(2).rstrip()
	
	#creates wiki page containing the default template
	def create_default_wikitemplate_page(self):
		pagecontent = """\
##master-page:PageTemplate
#format wiki
#language en
= ${title} =
Authors: ${wiki_author_lastnames}

== Content ==
TODO: Describe briefly

== Quotations ==
TODO: copy interesting sentences/paragraphs here

/* ATTENTION: Do not add content between autoupdate start and end markers by hand. It may get overwritten */
/* MENDELEY_AUTOUPDATE_START */
http://localhost/paper_bin/mendeley/${citation_key}.pdf <<BR>>
== Notes from Mendeley ==
{{{{#!wiki green/solid
{{{#!html 
${wiki_notes}
}}}
}}}}

== Link String ==
{{{
|| [[${citation_key}]] || ${title} ||
}}}

== Blob ==

{{{
${wiki_blob}
}}}

Mendeley created: ${wiki_mendeley_createtime} <<BR>>
Mendeley modified: ${wiki_mendeley_modtime} <<BR>>
/* MENDELEY_AUTOUPDATE_END */
Added to Wiki: @DATE@

----
CategoryPapers CategoryMendeleyGenerated ${wiki_category}
"""
		return(PageEditor(self.request, _wiki_base+'/Template').saveText(pagecontent, 0))
	
	#creates wiki page containing the default configuration stub
	def create_default_config_page(self):
		pagecontent = """\
== Configuration of Mendeley2Moin action plugin ==
/* ATTENTION: Do not add content between autoupdate start and end markers by hand. It may get overwritten */
/* MENDELEY_AUTOUPDATE_START */
{{{#!highlight python
consumer_key = insert_consumer_key_here
secret_key = insert_secret_key_here
#ID of mendeley folder to read
mendeley_folder = 0 #set to 0 for all documents
#set to True to get a copy of pdf in folder
enable_copy_pdf = False
copy_pdf_folder = /tmp
}}}
/* MENDELEY_AUTOUPDATE_END */
"""
		return(PageEditor(self.request, _wiki_base+'/Config').saveText(pagecontent, 0))
	
	#creates wiki log page, which guides user through installation
	def create_default_wikilog_page(self):
		pagecontent = """\
== Configuration steps on first run ==
On the first run you need to add your Mendeley consumer key and secret key to the config. TODO: Explain Mendeley OAuth

Go to [[http://dev.mendeley.com/applications/register/]] and register the application to get the consumer and secret key.

Please edit [[Mendeley2Moin/Config]] and add consumer and secret key. Then as next step click on [[/|Mendeley2Moin|&action=Mendeley2Moin]] to get the link to verify OAuth.
""" 
		return(PageEditor(self.request, _wiki_base+'/Log').saveText(pagecontent, 0))
	
	#creates default mendeley2moin overview wiki page
	def create_default_wikibase_page(self):
		pagecontent = """\
== Mendeley2Moin overview ==
|| Run plugin || [[/|Mendeley2Moin|&action=Mendeley2Moin]] ||
|| Edit Config || [[/Config]] ||
|| Edit Template || [[/Template]] ||
|| Review installation steps || [[/Log]] ||
""" 
		return(PageEditor(self.request, _wiki_base).saveText(pagecontent, 0))
	
	#inserts text at beginning of a wiki page
	def prepend_to_wiki_page(self, page_uri, heading, content):
		old_content = ''
		wiki_page = Page(self.request, page_uri)
		#if exists, get old page content
		if(wiki_page.exists()):
			old_content = wiki_page.get_raw_body()
		pagecontent = """\
== %(heading)s ==
%(content)s

%(old_content)s
""" % {'heading': heading, 'content': content, 'old_content': old_content }
		return(PageEditor(self.request, page_uri).saveText(pagecontent, 0))
	
	#Update existing wiki page for the given document. Only lines between AUTOUPDATE markers are updated, according to the Template page.
	def update_mendeley_doc(self, doc):
		old_pagecontent = Page(self.request, doc['citation_key']).get_raw_body()
		template = Page(self.request, _wiki_base+'/Template').get_raw_body()
		re_head = re.compile('^(.*MENDELEY_AUTOUPDATE_START[^\n]+)(.*?\n)([^\n]+MENDELEY_AUTOUPDATE_END.*)$', re.MULTILINE|re.DOTALL)
		#re_head = re.compile('^(.*MENDELEY\_AUTOUPDATE\_START)(.*)(MENDELEY\_AUTOUPDATE\_END.*)$', re.MULTILINE|re.DOTALL)
		result_template = re_head.search(template)
		template = result_template.group(2)
		blob = pformat(doc)
		doc['wiki_blob'] = blob
		doc['wiki_author_lastnames'] = join([x['surname'] for x in doc['authors']], ', ')
		doc['wiki_mendeley_createtime'] = date.fromtimestamp(doc['added']).strftime('%Y-%m-%d')
		doc['wiki_mendeley_modtime'] = date.fromtimestamp(doc['modified']).strftime('%Y-%m-%d')
		doc['wiki_category'] = ''
		if not 'notes' in doc:
			doc['notes'] = ''
		if(doc['type']=='Conference Proceedings'):
			doc['wiki_category'] = 'CategoryConference'
		elif(doc['type']=='Journal Article'):
			doc['wiki_category'] = 'CategoryJournal'
		re_nonlinebreak = re.compile('\\n')
		re_linebreak = re.compile('\<m:linebreak\>\<\/m:linebreak\>')
		re_italic = re.compile('\<([/]?)m:italic\>')
		re_bold = re.compile('\<([/]?)m:bold\>')
		re_underline = re.compile('\<([/]?)m:underline\>')
		re_right = re.compile('\<([/]?)m:right\>')
		re_center = re.compile('\<([/]?)m:center\>')
		doc['wiki_notes'] = re_center.sub('<br>', re_right.sub('<br>', re_underline.sub(r'<\1u>', re_bold.sub(r'<\1b>', \
			re_italic.sub(r'<\1i>',re_linebreak.sub('<br>',re_nonlinebreak.sub('', doc['notes'])))))))
		#<m:bold>123</m:bold>        <i>italic</i>        <m:underline>under</m:underline>        <br>        <m:center>center                </m:center>        <m:right>
		tmpl = Template(template)
		new_subpart = tmpl.safe_substitute(doc)
		result_pagecon = re_head.match(old_pagecontent)
		new_pagecontent = result_pagecon.group(1)+new_subpart+result_pagecon.group(3)
		return(PageEditor(self.request, doc['citation_key']).saveText(new_pagecontent, 0))
	
	#Create new wiki page for the given document. Page is created using the template from the Template page.
	def import_mendeley_doc(self, doc):
		blob = pformat(doc)
		doc['wiki_blob'] = blob
		doc['wiki_author_lastnames'] = join([x['surname'] for x in doc['authors']], ', ')
		doc['wiki_mendeley_createtime'] = date.fromtimestamp(doc['added']).strftime('%Y-%m-%d')
		doc['wiki_mendeley_modtime'] = date.fromtimestamp(doc['modified']).strftime('%Y-%m-%d')
		doc['wiki_category'] = ''
		if not 'notes' in doc:
			doc['notes'] = ''
		if(doc['type']=='Conference Proceedings'):
			doc['wiki_category'] = 'CategoryConference'
		elif(doc['type']=='Journal Article'):
			doc['wiki_category'] = 'CategoryJournal'
		re_nonlinebreak = re.compile('\\n')
		re_linebreak = re.compile('\<m:linebreak\>\<\/m:linebreak\>')
		re_italic = re.compile('\<([/]?)m:italic\>')
		re_bold = re.compile('\<([/]?)m:bold\>')
		re_underline = re.compile('\<([/]?)m:underline\>')
		re_right = re.compile('\<([/]?)m:right\>')
		re_center = re.compile('\<([/]?)m:center\>')
		doc['wiki_notes'] = re_center.sub('<br>', re_right.sub('<br>', re_underline.sub(r'<\1u>', re_bold.sub(r'<\1b>', \
			re_italic.sub(r'<\1i>',re_linebreak.sub('<br>',re_nonlinebreak.sub('', doc['notes'])))))))
		#<m:bold>123</m:bold>        <i>italic</i>        <m:underline>under</m:underline>        <br>        <m:center>center                </m:center>        <m:right>
		tmpl = Template(Page(self.request, _wiki_base+'/Template').get_raw_body())
		pagecontent = tmpl.safe_substitute(doc)
		return(PageEditor(self.request, doc['citation_key']).saveText(pagecontent, 0))
	
	#downloads first attachment with .pdf extension that is found
	def import_mendeley_attached_file(self, doc):
		output_dir = self.config['copy_pdf_folder']
		for mendeley_file in doc['files']:
			if mendeley_file['file_extension'].lower()=='pdf':
				filename = output_dir+'/'+doc['citation_key']+'.pdf'
				if not os.path.isfile(filename):
					response = self.mendeley_importer.mendeley.download_file(doc['id'], mendeley_file['file_hash'])
					if response.has_key('data'):
						os.umask(033)
						file_out = open(filename, 'w+b')
						file_out.write(response['data'])
						file_out.close()
						return(True)
				#abort after first downloaded file
				return(False)
		return(False)
	
	#handles action request from MoinMoin
	def handle_request(self):
		wiki_page_base = Page(self.request, _wiki_base)
		wiki_page_config = Page(self.request, _wiki_base+'/Config')
		form = self.request.form
		
		#=== Sanity checks: Create required pages if not exist, check if oauth config works ===
		
		#create _wiki_base page, if not exists
		if not Page(self.request, _wiki_base).exists():
			try:
				self.create_default_wikibase_page()
			except Exception as e:
				self.request.theme.add_msg('Could not create page "'+_wiki_base+'": '+pformat(e), 'error')
				Page(self.request, self.pagename).send_page()
				return
		#create Template page, if not exists
		if not Page(self.request, _wiki_base+'/Template').exists():
			try:
				self.create_default_wikitemplate_page()
			except Exception as e:
				self.request.theme.add_msg('Could not create page "'+_wiki_base+'/Template'+'": '+pformat(e), 'error')
				Page(self.request, self.pagename).send_page()
				return
		if wiki_page_config.exists():
			#parse config page and put as dict into self.config
			self.read_config(wiki_page_config)
		else:
			#create Log page, if not exists
			try:
				if not Page(self.request, _wiki_base+'/Log').exists():
					self.create_default_wikilog_page()
			except Exception as e:
				self.request.theme.add_msg('Could not create page "'+_wiki_base+'/Log": '+pformat(e), 'error')
				Page(self.request, self.pagename).send_page()
				return
			#create Config page, if not exists
			try:
				self.create_default_config_page()
			except Exception as e:
				self.request.theme.add_msg('Could not create page "'+_wiki_base+'/Config'+'": '+pformat(e), 'error')
				Page(self.request, self.pagename).send_page()
				return
			
			self.request.theme.add_msg('Welcome to Mendeley2Moin. Pages needed for this plugin have been created.', 'info')
			Page(self.request, _wiki_base+'/Log').send_page()
			return
		
		#Create MendeleyImporter instance and try to login using consumer/secret key and the file with authenticated tokens
		self.mendeley_importer = MendeleyImporter(self.config['consumer_key'], self.config['secret_key'])
		#Check if the user submitted the OAuth verifier
		if self.request.values.has_key('submitVerifier'):
			#parse serialized token and verifier
			try:
				self.mendeley_importer.set_verified_token(self.request.values['token'], self.request.values['verifier'])
			except ValueError as e:
				self.request.theme.add_msg('Could not authenticate tokens: '+pformat(e), 'error')
				Page(self.request, _wiki_base+'/Log').send_page()
				return
			#save tokens as pickled file as attachment to Config page
			self.mendeley_importer.save_keys(AttachFile.getAttachDir(self.request, _wiki_base+'/Config'))
			self.prepend_to_wiki_page(_wiki_base+'/Log', 'OAuth configuration completed', \
				'Access tokens have been saved [[attachment:%s/Config/mendeley_api_keys.pkl | here]]. Click here to run the plugin: [[/|Mendeley2Moin|&action=Mendeley2Moin]]\n'+\
				'\n(Or go to Mendeley2Moin overview page.)\n' % (_wiki_base))
			self.request.theme.add_msg('Tokens verified.' % (wikiutil.escape(self.mendeley_importer.mendeley.request_token)), 'info')
			Page(self.request, _wiki_base+'/Log').send_page()
			return
		#Try to read file with authenticated tokens. They are supposed to be an attachment of the Config page
		attachment = u'mendeley_api_keys.pkl'
		if not AttachFile.exists(self.request, _wiki_base+'/Config', attachment):
			#If file with authenticated tokens does not exist, request URL and write it as Log message to the user
			try:
				auth_url = self.mendeley_importer.get_auth_url()
			except Exception as e:
				self.request.theme.add_msg('Could not request OAuth URL: '+pformat(e), 'error')
				wiki_page_base.send_page()
				return
			self.request.theme.add_msg('Register token on: '+auth_url, 'info')
			try:
				self.prepend_to_wiki_page(_wiki_base+'/Log', 'Step two: Register your OAuth token on mendeley.com', """\
 * If you have a backup of the file {{{mendeley_api_keys.pkl}}}, upload it here [[attachment:%s/Config/mendeley_api_keys.pkl]].
 * Otherwise [[%s|click here]] to register your token on mendeley.com. Then enter the verification code here: 
{{{#!html 
<form action="submit" method="GET">
<input type="hidden" name="action" value="Mendeley2Moin" />
<input type="hidden" name="token" value="%s" />
<input type="text" name="verifier" value="" size="36" />
<input type="submit" name="submitVerifier" value="Submit" />
</form>
}}}
""" % (_wiki_base, auth_url, wikiutil.escape(self.mendeley_importer.mendeley.request_token.to_string())))
			except Exception as e:
				self.request.theme.add_msg('Could not edit page "'+_wiki_base+'/Log": '+pformat(e), 'error')
				Page(self.request, self.pagename).send_page()
				return
			Page(self.request, _wiki_base+'/Log').send_page()
			return
		
		#Get path of file with authenticated tokens and load it.
		self.config['api_keys_pkl_dir'] = AttachFile.getAttachDir(self.request, _wiki_base+'/Config')
		try:
			self.mendeley_importer.load_keys(self.config['api_keys_pkl_dir'])
		except Exception as e:
			self.request.theme.add_msg('Could not authenticate to Mendeley: '+pformat(e)+traceback.format_exc(), 'error')
			Page(self.request, self.pagename).send_page()
			return
		
		#=== Start with actual plugin ===
		
		#read in documents and folders from Mendeley
		logstring = ''
		try:
			text_output = '=== Mendeley Documents ===\n'
			fold = self.mendeley_importer.get_folders()
			docs = self.mendeley_importer.get_documents(int(self.config['mendeley_folder']))
		except ValueError as e:
			self.request.theme.add_msg('Error while calling Mendeley API: '+pformat(e)+traceback.format_exc(), 'error')
			Page(self.request, self.pagename).send_page()
			return
		
		#if GET parameter 'import' is set, import/update the appropriate documents
		if self.request.values.has_key('import'):
			import_id = self.request.values['import']
			for doc in docs:
				if import_id=='all' or import_id=='new' or import_id==doc['id']:
					try:
						#If wiki page for document exists, update it. Otherwise create new page and import.
						if Page(self.request, doc['citation_key']).exists():
							if import_id!='new':
								self.update_mendeley_doc(doc)
								logstring += 'Successfully updated %s\n' % (doc['citation_key'])
						else:
							self.import_mendeley_doc(doc)
							logstring += 'Successfully imported %s\n' % (doc['citation_key'])
					except PageEditor.Unchanged:
						pass
					#Download files attached to documents
					if self.config['enable_copy_pdf']=='True':
						try:
							#If wiki page for document exists, update it. Otherwise create new page and import.
							if Page(self.request, doc['citation_key']).exists():
								if import_id!='new':
									if self.import_mendeley_attached_file(doc):
										logstring += ' -> Downloaded file %s.pdf\n' % (doc['citation_key'])
									#raise ValueError("asdf")
							else:
								self.import_mendeley_attached_file(doc)
						except Exception as e:
							logstring += 'WARNING: Could not import attached file from mendeley: %s\n' % (pformat(e))
		
		#prepare print out of documents with links to pages and links to import/update
		for doc in docs:
			if(Page(self.request, doc['citation_key']).exists()):
				text_output += "|| [["+doc['citation_key']+"]] || "+doc['title']+"|| <<Action(Mendeley2Moin, Update, import="+doc['id']+")>> ||\n"
			else:
				text_output += "|| "+doc['citation_key']+" || "+doc['title']+"|| <<Action(Mendeley2Moin, Import, import="+doc['id']+")>> ||\n"
		text_output += '\n<<Action(Mendeley2Moin, Import all documents, import=all)>>\n'
		#prepare print out of list of folders
		text_output += '\n=== Mendeley Folders ===\n|| ID || Name ||\n'
		for folder in fold:
			text_output += '|| %s || %s ||\n' % (folder['id'], folder['name'])
		
		#now print all prepared stuff out
		self.request.formatter.page = Page(self.request, self.pagename)
		self.output_content_with_header_and_footer(self.request.formatter.rawHTML('<pre>'+wikiutil.escape(logstring)+'</pre>')+\
			wikiutil.renderText(self.request, WikiParser, text_output))
	
	#convenience method to print out content given as parameter with headers and footers
	def output_content_with_header_and_footer(self, text):
		try:
			self.request.emit_http_headers()
		except AttributeError:
			try:
				self.request.http_headers()
			except AttributeError:
				pass
		self.request.theme.send_title(self.request.getText('Mendeley2Moin'), pagename=self.pagename, msg=None)
		self.request.write(self.request.formatter.startContent("content"))
		self.request.write(text)
		self.request.write(self.request.formatter.endContent())
		self.request.theme.send_footer(self.pagename)
		self.request.theme.send_closing_html()
	
	#convenience method to print out header stuff before content
	def output_header(self):
		try:
			self.request.emit_http_headers()
		except AttributeError:
			try:
				self.request.http_headers()
			except AttributeError:
				pass
		self.request.theme.send_title(self.request.getText('Mendeley2Moin'), pagename=self.pagename, msg=None)
		self.request.write(self.request.formatter.startContent("content"))
	
	#convenience method to print out footer stuff after content
	def output_footer(self):
		self.request.write(self.request.formatter.endContent())
		self.request.theme.send_footer(self.pagename)
		self.request.theme.send_closing_html()

