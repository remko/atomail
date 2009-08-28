#!/usr/bin/env python
# coding=utf-8

################################################################################
# Module information
################################################################################

"""
  A package for converting mail into Atom (RFC 4287) RSS feeds.

  Mail messages can be retrieved from different sources, including
  stdin, NNTP, POP3, IMAP, and local mailboxes.

  For details on available parameters, use the --help option.
  Help and more information can be found on 
    http://el-tramo.be/software/atomail
"""

__all__ = ['MessageFeed', 'MailSource', 'PipeSource', 'MailboxSource', 'IMAPSource', 'POP3Source', 'NNTPSource', 'ATOM_NS' ]
__author__ = 'Remko Tronçon'
__version__ = '0.9-dev'
__copyright__ = """
  Copyright (C) 2006  Remko Tronçon

  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software
  Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
  """

# TODO:
# - Warn about missing SSL

################################################################################
# Imports
################################################################################

import sys, os.path, optparse, datetime, email, email.header, email.Utils, time, re, xml
import string, logging, md5
from xml.dom import minidom
import nntplib, imaplib, poplib, mailbox

################################################################################
# Constants
################################################################################

PROGRAM_NAME = 'AtoMail'
PROGRAM_URI = 'http://el-tramo.be/software/atomail'
PROGRAM_USAGESTRING = "usage: %prog [options] file"
PROGRAM_VERSIONSTRING = PROGRAM_NAME + ' ' + __version__ + '\nWritten by ' + __author__ + '\n' + 'For more information, please visit ' + PROGRAM_URI

ATOM_NS = 'http://www.w3.org/2005/Atom'
DEFAULT_ENCODING = "iso8859-1" # This will be used to decode headers if no encoding is specified. Should probably be smarter about this. See usage for more info

################################################################################
# Auxiliary functions and classes
################################################################################

class TZ(datetime.tzinfo) :
  def __init__(self,hours=0) :
    self.hours = hours
    
  def utcoffset(self, dt) : 
    return datetime.timedelta(hours=self.hours)

def message_id(message) :
  hash = md5.new()
  if message['From'] :
    hash.update(message['From'])
  if message['Subject'] :
    hash.update(message['Subject'])
  if message['Date'] :
    hash.update(message['Date'])
  return hash.hexdigest()

def message_date(message) :
  date = email.Utils.parsedate(message["Date"])
  if date != None :
    return datetime.datetime(date[0],date[1],date[2],date[3],date[4],date[5],date[6],TZ(date[7]))
  else :
    logging.warning('Unable to parse date \'' + message['Date'] + '\'')
    return datetime.datetime(datetime.MINYEAR,1,1)

def message_contents(message, default_charset) :
  contents = []
  if message.is_multipart() :
    for submessage in message.get_payload() :
      contents += message_contents(submessage, default_charset)
  else :
    payload = message.get_payload(decode=True)
    if payload : 
      content = unicode(payload, get_charset(message, default_charset), "replace")
      content_type = message.get_content_type()
      if content_type == 'text/plain' :
        contents = [('text',content)]
      if content_type == 'text/html' :
        contents = [('html',content)]
    else :
      logging.warning('Missing payload in message')
  return contents

def current_datetime() :
  now = datetime.datetime.now()
  current_tz = round(float((datetime.datetime.now() - datetime.datetime.utcnow()).seconds)/3600)
  if current_tz > 12 :
    current_tz -= 24
  return now.replace(tzinfo=TZ(current_tz))

def from_atom_date(date) :
  microseconds = 0
  timezone = 0
  suffix = date[19:]
  m = re.match("(\.(?P<microseconds>\d+))?(?P<timezone>(\+|-)\d\d)?",suffix)
  if m != None :
    if m.group('microseconds') :
      microseconds = int(m.group('microseconds'))
    if m.group('timezone') :
      timezone = int(m.group('timezone'))
  return datetime.datetime(int(date[0:4]),int(date[5:7]),int(date[8:10]),int(date[11:13]),int(date[14:16]),int(date[17:19]),microseconds,TZ(timezone))

def entry_date(entry) :
  updated_nodes = entry.getElementsByTagName('updated')
  if updated_nodes :
    date = from_atom_date(updated_nodes[0].childNodes[0].data)
  else :
    date = datetime.datetime(datetime.MINYEAR,1,1)
  return date

def decode_header(header, default) :
  decoded_header = ""
  for (result, encoding) in email.header.decode_header(header if header else default) :
    # Some mails don't have an encoding in the header, yet they do encode the
    # header. We should do trial and error here, but for now assume it's 
    # Iso8859-1.
    if not encoding :
      encoding = DEFAULT_ENCODING
    decoded_header += result.decode(encoding, "ignore") if encoding else result
  return decoded_header

def get_charset(message, default="ascii"):
  if message.get_content_charset() :
    return message.get_content_charset()
  elif message.get_charset() :
    return message.get_charset()
  else :
    return default

################################################################################
# MessageFeed 
################################################################################

class MessageFeed :
  """A class representing an (Atom) feed of messages"""

  def __init__(self, filename, uri, title, max_items, max_time, strip_subject) :
    """Initialize the feed"""
    logging.info('Initializing the message feed')
    self.filename = filename
    self.max_items = max_items
    self.max_time = max_time
    self.strip_subject = strip_subject
    self.doc = xml.dom.minidom.getDOMImplementation().createDocument(ATOM_NS, 'feed', None)
    self.doc.documentElement.setAttribute('xmlns',ATOM_NS)
    self.set_id(uri)
    self.set_updated(datetime.datetime(datetime.MINYEAR,1,1))
    if os.path.isfile(self.filename) :
      logging.info('Reading feed from ' + self.filename)
      try : 
        self.doc = minidom.parse(self.filename)
        self.doc.normalize()
      except :
         logging.warning('Unable to parse feed. Resetting the file.')
    else :
      logging.info('Creating new file ' + self.filename)
    self.set_link(uri)
    self.set_title(title)
    
    
  def __del__(self) :
    """Destroy the feed"""
    self.doc.unlink()
    

  def add_message(self, message) :
    """Adds a new message to the feed"""
    logging.info('Adding new message to the feed')

    # Create a new entry
    entry = self.doc.createElement('entry')
    
    # ID
    id = self.doc.createElement('id')
    id.appendChild(self.doc.createTextNode(self.id() + '#' + message_id(message)))
    entry.appendChild(id)

    # Author
    from_address = decode_header(message["From"], "Anonymous")
    (name,address) = email.Utils.parseaddr(from_address)
    author = self.doc.createElement('author')
    author_name = self.doc.createElement('name')
    if name and address :
      author_name.appendChild(self.doc.createTextNode(name))
      author_email = self.doc.createElement('email')
      author_email.appendChild(self.doc.createTextNode(address))
      author.appendChild(author_email)
    else :
      author_name.appendChild(self.doc.createTextNode(from_address))
    author.appendChild(author_name)
    entry.appendChild(author)
    logging.debug('Author: ' + name + ' (' + address + ')')
    
    # Date
    date = message_date(message)
    published = self.doc.createElement("published")
    published.appendChild(self.doc.createTextNode(date.isoformat()))
    entry.appendChild(published)
    logging.debug('Published: ' + date.isoformat())
    
    # Updated
    updated = self.doc.createElement('updated')
    updated.appendChild(self.doc.createTextNode(current_datetime().isoformat()))
    entry.appendChild(updated)
    
    # Subject
    title = self.doc.createElement('title')
    title_text = decode_header(message["Subject"], "(No Subject)")
    if self.strip_subject :
      title_text = re.sub('\[[a-zA-Z0-9:_\. -]*\]\s*','',title_text)
    title.appendChild(self.doc.createTextNode(title_text))
    entry.appendChild(title)
    logging.debug('Title: ' + title_text)

    # Content
    content = self.doc.createElement('content')
    contents = message_contents(message, get_charset(message))
    if contents :
      # Add the preferred content
      contents.sort(lambda x, y : cmp(x,y))
      (content_type,content_text) = contents[0]
      content.setAttribute('type',content_type)
      content.appendChild(self.doc.createTextNode(content_text))
    else :
      logging.warning('No valid contents found')
      content.appendChild(self.doc.createTextNode(title_text))
    entry.appendChild(content)

    # Add the entry to the feed
    self.doc.documentElement.appendChild(entry)

  def set_generator(self) :
    """Updates the generator (program) of this feed"""
    generator = self.doc.createElement('generator')
    generator.appendChild(self.doc.createTextNode(PROGRAM_NAME))
    generator.setAttribute('version', __version__)
    generator.setAttribute('uri', PROGRAM_URI)
    self.replace_element(generator)

  def id(self) :
    """Returns the unique identifier of this feed"""
    return filter(lambda x : x.parentNode == self.doc.documentElement, self.doc.documentElement.getElementsByTagName('id'))[0].childNodes[0].data
  
  def contains_message(self, message) :
    id = message_id(message)
    feed_id = self.id()
    for entry in self.doc.getElementsByTagName('entry') :
      for entry_id_element in entry.getElementsByTagName('id') :
        entry_id = entry_id_element.childNodes[0].data
        if entry_id == feed_id + '#' + id :
          return True
    return False

  def updated(self) :
    """Returns the last time this feed was updated (as a datetime object)"""
    return from_atom_date(filter(lambda x : x.parentNode == self.doc.documentElement, self.doc.documentElement.getElementsByTagName('updated'))[0].childNodes[0].data)

  def set_id(self, id) :
    """Sets the unique identifier of this feed"""
    self.set_element_text('id', id)
    
  def set_title(self, title) :
    """Sets the title of this feed"""
    self.set_element_text('title', title)
    
  def set_link(self, uri) :
    """Sets the URI of this feed"""
    link = self.doc.createElement('link')
    link.setAttribute('rel', 'self')
    link.setAttribute('href', uri)
    self.replace_element(link)

  def set_element_text(self,tagname,value) :
    """Sets the text contents of a toplevel element of this feed to this string"""
    text = self.doc.createElement(tagname)
    text.appendChild(self.doc.createTextNode(value))
    self.replace_element(text)

  def replace_element(self,element) :
    """Replaces a toplevel element in the feed"""
    # Try to find the relevant node node
    nodes = filter(lambda x : x.parentNode == self.doc.documentElement, self.doc.documentElement.getElementsByTagName(element.tagName))
    if nodes :
      self.doc.documentElement.replaceChild(element,nodes[0])
    
    # Create a new node (before the entries)
    entries = self.doc.documentElement.getElementsByTagName('entry')
    if len(entries) > 0 :
      self.doc.documentElement.insertBefore(element,entries[0])
    else :
      self.doc.documentElement.appendChild(element)
  
  def trim_entries(self) :
    """Removes all the redundant and outdated entries"""
    logging.info('Trimming entries')
    entries = self.doc.documentElement.getElementsByTagName('entry')
    entries.sort(lambda x, y : cmp(entry_date(x),entry_date(y)))

    # Trim based on the maximum number of items
    if self.max_items > 0 :
      while len(entries) > self.max_items :
        logging.debug('Removing redundant entry')
        self.doc.documentElement.removeChild(entries.pop(0))
    
    # Trim based on the maximum time elapsed
    if self.max_time > 0 :
      max_datetime = current_datetime() - datetime.timedelta(minutes=self.max_time)
      while entries and entry_date(entries[0]) < max_datetime :
        logging.debug('Removing outdated entry')
        self.doc.documentElement.removeChild(entries.pop(0))
      
  def set_updated(self, time) :
    """Sets the updated time as a datetime object."""
    self.set_element_text('updated', time.isoformat())
    
  def save(self) :
    """Saves this feed to file.

    The generator is updated, and the elements are trimmed before the feed
    is saved"""
    logging.info('Saving feed')
    self.set_generator()
    self.trim_entries()
    logging.info('Writing feed to file ' + self.filename)
    out = open(self.filename, 'w')
    out.write(self.doc.toxml('utf-8'))
    out.close()


################################################################################
# MailSource
################################################################################

class MailSource :
  """An abstract class used to retrieve mail messages from a certain source.
  
  Subclasses must implement the messages() function, which retrieves the
  messages from the concrete source."""

  def messages(self) :
    """Retrieve all messages (in reverse order)"""
    pass

class PipeSource(MailSource) :
  """A class that retrieves messages from stdin"""

  def messages(self) :
    logging.info('Reading message from stdin')
    return [email.message_from_file(sys.stdin)]


class MailboxSource(MailSource) :
  """A class that retrieves messages from a mailbox file.
  
  The type of the mailbox file needs to be specified as a mailbox class.
  """
  
  def __init__(self, filename, type) :
    logging.info('Initializing mailbox source (file=' + filename + ',type=' + type.__name__ + ')')
    self.type = type
    self.filename = filename
    
  def messages(self) :
    logging.info('Reading mails from ' + self.filename) 
    file = open(self.filename,'r')
    mailbox = self.type(file, email.message_from_file)
    mails = []
    mail = mailbox.next()
    while mail != None :
      mails.append(mail)
      mail = mailbox.next()
    mails.reverse()
    return mails


class POP3Source(MailSource) :
  """A class that retrieves messages from a POP3 server."""
  
  def __init__(self, host, port, user, password, ssl=False) :
    logging.info('Initializing POP3 client')
    if ssl :
      pop = poplib.POP3_SSL
    else :
      pop = poplib.POP3
    if port :
      self.pop = pop(host,port)
    else :
      self.pop = pop(host)
    logging.info('Authenticating')
    self.pop.user(user)
    self.pop.pass_(password)

  def messages(self) :
    logging.info('Retrieving POP3 list')
    nb_messages = len(self.pop.list()[1])
    logging.debug(str(nb_messages) + ' messages waiting')
    while nb_messages > 0 :
      message_text = ''
      for j in self.pop.retr(nb_messages)[1]:
        message_text += j + '\n'
      message = email.message_from_string(message_text)
      if message :
        yield message
      else :
        logging.warn('Unable to parse message:\n' + message_text)
      nb_messages -= 1


class NNTPSource(MailSource) :
  """A class that retrieves messages from an NNTP server."""

  def __init__(self, host, port, group, user, password) :
    logging.info('Initializing NNTP client')
    if port :
      self.nntp = nntplib.NNTP(host,port,user=user,password=password)
    else :
      self.nntp = nntplib.NNTP(host,user=user,password=password)
    self.group = group

  def messages(self) :
    logging.info('Retrieving article list')
    result = self.nntp.group(self.group)
    first = int(result[2])
    last = int(result[3])
    while last >= first :
      logging.debug('Retrieving header of article ' + str(last))
      try :
        head = string.join(self.nntp.head(str(last))[3],'\n')
        message = email.message_from_string(head)
        body = string.join(self.nntp.body(str(last))[3],'\n')
        message = email.message_from_string(head + '\n' + body)
        if message :
          yield message
        else :
          logging.warn('Unable to parse message:\n' + head + '\n' + body)
      except nntplib.NNTPTemporaryError :
        pass
      last -= 1


class IMAPSource(MailSource) :
  """A class that retrieves messages from an IMAP server."""

  def __init__(self, host, port, user, password, mailbox, ssl=False) :
    logging.info('Initializing IMAP client')
    if ssl :
      imap = imaplib.IMAP4_SSL
    else :
      imap = imaplib.IMAP4
    if port :
      self.imap = imap(host,port)
    else :
      self.imap = imap(host)
    logging.info('Authenticating')
    self.imap.login(user,password)
    if mailbox :
      logging.info('Opening mailbox \'' + mailbox + '\'')
      self.imap.select(mailbox=mailbox)
    else :
      logging.info('Opening INBOX')
      self.imap.select()

  def messages(self) :
    logging.info('Retrieving relevant message numbers')
    _, msgnums =  self.imap.search(None,'ALL')
    msg_numbers = msgnums[0].split()
    while msg_numbers :
      msg_number = msg_numbers.pop()
      logging.info('Fetching article ' + msg_number)
      typ, data = self.imap.fetch(msg_number, '(RFC822)')
      message = email.message_from_string(data[0][1])
      if message :
        yield message
      else :
        logging.warn('Unable to parse message:\n' + data[0][1])
      

################################################################################
# Main program
################################################################################

if __name__ == "__main__" :
  # Parse the arguments
  parser = optparse.OptionParser(usage=PROGRAM_USAGESTRING, version=PROGRAM_VERSIONSTRING)
  parser.add_option('-q','--quiet', help='Turn off logging', action='store_const', dest='loglevel', const=logging.ERROR, default=logging.WARNING)
  parser.add_option('-v','--verbose', help='Turn on verbose logging', action='store_const', dest='loglevel', const=logging.INFO)
  parser.add_option('-d','--debug', help='Turn on debug logging', action='store_const', dest='loglevel', const=logging.DEBUG)
  parser.add_option('-l','--logfile', metavar='FILE', help='Send log to a file (instead of stderr)')
  parser.add_option('-m', '--mode', metavar='MODE', help='The mode in which this script should operate (pipe,mbox,maildir,pop3,pop3-ssl,imap,imap-ssl,nntp). Default: %default', type='choice', choices=['pipe','mbox','maildir','pop3','pop3-ssl','imap','imap-ssl','nntp'], default='pipe')
  parser.add_option('-u', '--uri', metavar='URI', help='The URI of the target feed')
  parser.add_option('-t', '--title', metavar='TITLE', help='The title of the target feed', default='AtoMail feed')
  parser.add_option('', '--max-items', metavar='ITEMS', help='The maximum number of items in the feed. Default: %default', type='int', default=10)
  parser.add_option('', '--max-time', metavar='MINUTES', help='The maximum number of elapsed minutes for items in the feed', type='int', default=-1)
  parser.add_option('-s', '--strip-subject', action='store_true', dest='strip_subject', default=False, help='Strip mailing-list headers from the subject')
  parser.add_option('-f','--file', metavar='FILE', help='The file or directory to read messages from (mbox,maildir)')
  parser.add_option('','--host', metavar='HOST', help='The host to receive messages from (pop3,pop3-ssl,imap,imap-ssl,nntp)')
  parser.add_option('','--port', metavar='PORT', type='int', help='The host port to receive messages from (pop3,pop3-ssl,imap,imap-ssl,nntp)')
  parser.add_option('','--user', metavar='USERNAME', help='The user to authenticate with (pop3,pop3-ssl,imap,imap-ssl,nntp)')
  parser.add_option('','--password', metavar='PASSWORD', help='The password to authenticate with (pop3,pop3-ssl,imap,imap-ssl,nntp)')
  #parser.add_option('','--mailbox', metavar='PASSWORD', help='The IMAP mailbox to open (imap)')
  parser.add_option('','--group', metavar='GROUP', help='The group from which to retrieve messages (nntp)')
  (options, args) = parser.parse_args()

  # Initialize the logger
  if options.logfile :
    handler = logging.FileHandler(options.logfile)
  else :
    handler = logging.StreamHandler()
  handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
  logging.getLogger().addHandler(handler)
  logging.getLogger().setLevel(options.loglevel)

  # Get the filename
  if len(args) != 1 :
    sys.exit('Filename missing')
  filename = args[0]
  
  # Check hostname
  if options.mode in ('pop3','pop3-ssl','imap','imap-ssl','nntp') and not options.host :
    sys.exit('Host missing')
  
  if options.mode in ('pop3','pop3-ssl','imap','imap-ssl') and not options.user :
    sys.exit('Username missing')
  
  if options.mode in ('pop3','pop3-ssl','imap','imap-ssl') and not options.password :
    sys.exit('Password missing')

  if options.mode in ('mbox','maildir') and not options.file :
    sys.exit('Mailbox file or directory missing')

  if options.mode == 'nntp' and not options.group :
    sys.exit('Group missing')

  # Substitute defaults if necessary
  if not options.uri :
    logging.warning('Feed URI missing. Using default URI.')
    options.uri = 'http://example.com/' + os.path.basename(filename)
    
  # Initialize the feed
  feed = MessageFeed(filename = filename, uri = options.uri, title = options.title, max_items = options.max_items, max_time = options.max_time, strip_subject = options.strip_subject)
  updated_time = feed.updated()
  current_time = current_datetime()
  logging.debug('Current time: ' + str(current_time))
  logging.debug('Feed last updated: ' + str(updated_time))
  
  # Initialize the message source
  logging.info('Initializing the message source')
  if options.mode == "mbox" :
    source = MailboxSource(options.file, mailbox.PortableUnixMailbox)
  elif options.mode == "maildir" :
    source = MailboxSource(options.file, mailbox.Maildir)
  elif options.mode == "pop3" : 
    source = POP3Source(options.host, options.port, options.user, options.password)
  elif options.mode == "pop3-ssl" : 
    source = POP3Source(options.host, options.port, options.user, options.password, ssl=True)
  elif options.mode == "imap" : 
    source = IMAPSource(options.host, options.port, options.user, options.password, None)
  elif options.mode == "imap-ssl" : 
    source = IMAPSource(options.host, options.port, options.user, options.password, None, ssl=True)
  elif options.mode == "nntp" : 
    source = NNTPSource(options.host, options.port, options.group, options.user, options.password)    
  else :
    source = PipeSource()
    
  # Determine the date from which messages should be retrieved
  if options.max_time > 0 :
    from_time = max(current_time - datetime.timedelta(minutes=options.max_time),updated_time)
  else :
    from_time = updated_time

  # Add available messages to the feed
  count = 0
  for message in source.messages() :
    if feed.contains_message(message) :
      logging.info('Message already in feed. Stopped retrieving.')
      break
    else :
      feed.add_message(message)
      count += 1
      if options.max_items > 0 and count > options.max_items :
        logging.info('Maximum # of items reached. Stopped retrieving.')
        break
    
  # Add the messages to the feed
  feed.set_updated(current_time)
  feed.save()
