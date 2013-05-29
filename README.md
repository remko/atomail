# [AtoMail](http://el-tramo.be/software/atomail)

## About

AtoMail is a Python script that converts email (or other messages) into an 
([Atom](http://www.ietf.org/rfc/rfc4287)) RSS feed. This is for example 
useful for tracking announcement mailinglists in your favorite RSS reader, if no classic RSS feed is available.
Mail can be retrieved from many different sources, including local mailboxes, remote mailboxes (POP3/IMAP4), and usenet newsgroups (NNTP). The goal of AtoMail is to be clean, modular, well documented, and easy to modify.

Beware that AtoMail is still in alpha stage, and that it probably contains
bugs.


## Usage

AtoMail can be used to create feeds of messages coming from many different sources. The source from which AtoMail is to retrieve the messages is set by the `--mode` parameter. Here are some example use cases.

### Piping messages

AtoMail by default reads a mail message from stdin, and adds it as an entry to a given feed file. This is called 'pipe' mode. This mode makes it very easy to create RSS feeds of mailinglists using a simple a procmail rule:

		:0
		* ^TO_somemailinglist@example.com
		| atomail.py --title 'Some Mailinglist' --uri='http://mysite.com/somemailinglist.xml' --strip-subjects $HOME/public_html/somemailinglist.xml

### Getting messages from local mailboxes

AtoMail can be used to create an RSS feed of local mailboxes (in mailbox or maildir format), specified by the `--file` flag:

		atomail.py --title 'Some Mailbox' --uri='http://mysite.com/somemailbox.xml' $HOME/public_html/somemailbox.xml --mode=mbox --file $HOME/mail/somemailbox

### Getting messages from POP3/IMAP

Mail can be retrieved from remote POP3 or IMAP accounts:

		atomail.py --title 'Some Mailbox' --uri='http://mysite.com/somemailbox.xml' $HOME/public_html/somemailbox.xml --mode=pop3 --host pop.myserver.com --user=myusername --password=mypassword


### Getting messages from Usenet/Newsgroups/NNTP

AtoMail can be used to create RSS feeds from (NNTP) usenet newsgroups:

		atomail.py --title 'Some Mailbox' --uri='http://mysite.com/somegroup.xml' $HOME/public_html/somegroup.xml --mode=nntp --host news.myserver.com --group=comp.some.group

## Related software/sites

Several other email to RSS services and programs exist. Here are a few, together with a brief comparison with AtoMail:

- mail2rss.org: This website provides a mail2rss service without needing extra setup. However, it does not give you full control over your RSS feed, is not very reliable (in my experience), and of course requires you to deliver all your mail to a third party. Notice that it should be easy to set up a similar service using AtoMail.
- [mailbucket.org](http://mailbucket.org/): Another mail-to-RSS gateway, yet currently more reliable than mail2rss.org. The same remarks apply as for mail2rss.org.
- [mail2rss](http://mail2rss.sourceforge.net/): Requires .NET, which is a pretty heavy requirement. This application works by querying your mailbox, which can be done using AtoMail as well.
