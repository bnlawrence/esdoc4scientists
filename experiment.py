import os, re
os.environ['ESDOC_API'] = 'https://api.es-doc.org'
import pyesdoc as esd
import unittest
from jinja2 import Template


# pip install esdoc
# weasyprint is python3 only now ... but pyesdoc isn't python3 yet, so to get
# the last python2.7 version:
# pip install weasyprint==0.42.3
# Unfortunately we also depend on system gtk libraries, which you may or
# may not have easily available. This is how I got them on Mac Os Mojave
# (to avoid error: OSError: dlopen() failed to load a library: cairo / cairo-2 / cairo-gobject-2)
# brew install cairo pango gdk-pixbuf libxml2 libxslt libffi
# More information on dependencies for other platforms here:
# https://weasyprint.readthedocs.io/en/stable/install.html

# Also need to avoid this error: "ValueError: unknown locale: UTF-8" by
# adding the following to your path:
# export LANG=en_US.UTF-8

from weasyprint import HTML, CSS

# I do not know why the header font size (ename) is not respected.
# This is the one column-width CSS.

esCSS = """
    * {font-family: "Times New Roman", Times, serif; font-size:10pt}
    .ename{background-color:gray; color:white; text-align: center; font-size:24pt; font-weight: bold}
    .lname{text-align: center; padding: 2px}
    .bold{font-weight: bold}
    .italic{font-style: italic}
    table tr td { border: 1px solid black; padding:4px}
    td {vertical-align: top}
    .f {table-layout: fixed; width: 8.8cm;}
    ul {list-style-position: outside; padding-left:0; margin:0 0 0 0.3cm; }
    li {padding-left:0.05cm; font-size:9pt}
    """

class Repo(object):
    """ View on a repository suitable for extracting documents in pyesdoc format.
    Provides methods to get  particular document given name and document type,
    or to get by documnent id.

    Expect the former to be used when starting from a particular document found via
    the web interface, and the latter by code which is traversing document links
    from within the starting document. """

    def __init__(self, source='cmip6'):

        """ Initialise with repository of choice, default is CMIP6"""

        self.source = source

        # We keep a dictionary of document sets so each call to getbyname does not need
        # to get the document set first, unless that document set has not previously been requested.

        self.documents = {}

    def getbyname(self, name, doctype='experiment'):

        """ Get a particular document, given knowledge of it's name and document type """

        if doctype not in self.documents:
            self.documents[doctype] = esd.search(self.source, doctype)
        return self.documents[doctype].load_document(name)

    def getbyid(self, id):

        """ Get a particular document when you know it's id"""

        return esd.retrieve(id)


class Doc(object):

    """ Base mixin class for rendering. The basic idea is that we use a Jinja template
    to create an HTML table. The contents of the table are populated from the python
    class instances with document data. The document is rendered to HTML using the
    html method, and then to PDF from HTML using the actual render method. This
    class is never used itself, only the subclasses actually do anything."""

    # Note the intimate link between the template and the extraction code.
    # In both cases (onecol, twocol) we have material that we want to replace with
    # words from the actual esdoc documents, which we've called noted as XXX, XX1, OR XX2.
    #

    header = """
          <tr class="ename"><td colspan="1">{{d.name}} ({{mips}})</td></tr>
          <tr class="lname"><td colspan="1"><span class="italic">{{d.long_name}}</span></td></tr>
          <tr><td colspan="1"><span  class="bold">Description:</span> {{d.description}}</td></tr>
          <tr><td colspan="1"><span class="bold">Rationale: </span>{{d.rationale}}</td></tr>
          <tr class="lname"><td colspan="1"><span class="bold"> {{children}} </span></td></tr>
          """

    onecol = """{% for r in related %}
        <tr><td><span class="bold">{{r.name}}</span>: {{r.description}}
        XXX</td></tr>
        {% endfor %}
        """

    twocol = """{% for r in related %}
        <tr><td><span class="bold">{{r[0].name}}</span>: {{r[0].description}}XX1</td>
        <td>{% if r[1] != None %} <span class="bold">{{r[1].name}}</span>: {{r[1].description}}XX2</td> 
        {% else %} <td></td> {% endif %}</tr>
        {% endfor %}
        """

    def _settemplates(self, onecol, twocol):
        """ Set up the templates """

        self.template = """
        <table class="f"><tbody>
           %s
           %s
           </tbody></table>
           """ % (self.header, onecol)

        # This is suitable for two column width.
        self.wide_template = """
           <table class="f"><tbody>
           %s
           %s
           </tbody></table>
           """ % (self.header.replace("1", "2"), twocol)

    def html(self, children, ordering):

        """ Mixin method. Not implemented in the base class."""

        raise NotImplementedError

    def _html(self, children, wide=False, additional="", ordering='normal'):

        """ Render to html. This should be called by the parent class's
        html method. """

        def sorter(r):

            """ provides a number to sort related in ascending length of description"""

            ans = len(r.description)
            if additional:
                for rr in r.monkey_additional:
                    ans += len(rr)
            return ans

        # do we need the placeholder in the template for additional material?
        if additional == "":
            self.template = self.template.replace('XXX', "")
            self.wide_template = self.wide_template.replace('XX1', "")
            self.wide_template = self.wide_template.replace('XX2', "")

        if wide:

            if additional:
                a1 = additional.replace('r.monkey', 'r[0].monkey')
                a2 = additional.replace('r.monkey', 'r[1].monkey')
                self.wide_template = self.wide_template.replace('XX1',a1)
                self.wide_template = self.wide_template.replace('XX2',a2)

            # sort for similar lengths
            if ordering == 'normal':
                ordered = sorted(self.related, key=sorter)
                self.related = list(reversed(ordered))
            elif ordering == 'special':
                ordered = sorted(self.related[1:], key=sorter)
                self.related = [self.related[0], ordered[0]] + list(reversed(ordered[1:]))
            else:
                raise ValueError('html rendering with unexpected value of ordering %s' % ordering)
            pairs = zip(self.related[0::2], self.related[1::2])
            if len(pairs)*2 != len(self.related):
                pairs.append([self.related[-1], None])
            template = Template(self.wide_template)
            html = template.render(d=self.doc, related=pairs, mips=self.mips, children=children)
        else:
            if additional:
                self.template = self.template.replace('XXX',additional)
            template = Template(self.template)
            html = template.render(d=self.doc, related=self.related, mips=self.mips, children=children)
        return html


    def render(self, output_name, wide=False):

        """ Render to PDF if desired, by first getting the HTML version. """

        html = self.html(wide)
        print 'You can ignore the GLib-Gobject errors (if they occur)'
        if wide:
            HTML(string=html).write_pdf(
                output_name, stylesheets=[CSS(string=esCSS.replace("8.8cm", "18cm"))])
        else:
            HTML(string=html).write_pdf(
                output_name, stylesheets=[CSS(string=esCSS)])


class Experiment(Doc):

    """ This provides a view on an experiment document which is suitable
    for publication. That is, it provides a high quality PDF view which
    can be included as a figure/table in any document.
    Three steps: HTML layout, CSS style, PDF output.
    You will probably then want to crop the output pdf using a tool like pdfcrop.
    """

    additional_template = """{% if r.monkey_additional %} <br/> <span class="italic"> Additional Requirements:</span> <ul>
           {% for ar in r.monkey_additional %} <li>{{ar}}
           {% endfor %}</ul>{% endif %}"""

    def __init__(self, document):
        """ Initialise with an experiment document """
        self._settemplates(self.onecol, self.twocol)
        assert document.type_key == 'cim.2.designing.NumericalExperiment'
        self.doc = document

        # In most cases there is only one related mip.
        # Handle the edge case here rather than in template.
        mips = ''
        for m in document.related_mips:
            mips += m.name+', '
        self.mips = mips[:-2]

        self.related = []
        for r in self.doc.requirements:
            req = esd.retrieve(r.id)
            # Are there additional requirements?
            # If so, let's monkey patch their long names onto the linkage...
            # The other choice would be to have a requirements class WITH
            # it's own template.
            req.monkey_additional = []
            if req.additional_requirements:
                for rr in req.additional_requirements:
                    rreq = esd.retrieve(rr.id)
                    req.monkey_additional.append(rreq.long_name)
            self.related.append(req)

    def html(self, wide=False, ordering='special'):
        """ Render to html """
        return self._html('Requirements', wide, additional=self.additional_template)


class Mip(Doc):

    """ This provides a view on a MIP document which is suitable
    for publication. That is, it provides a high quality PDF view which
    can be included as a figure/table in any document.
    Three steps: HTML layout, CSS style, PDF output.
    You will probably then want to crop the output pdf using a tool like pdfcrop.
    """

    def __init__(self, document):

        """ Initialise with a MIP document """

        self._settemplates(self.onecol, self.twocol)
        assert document.type_key == 'cim.2.designing.Project'
        self.doc = document

        # We will populate the "mip" variable with the mip era
        self.mips = 'CMIP6'

        self.related = []
        for r in self.doc.required_experiments:
            self.related.append(esd.retrieve(r.id))

    def html(self, wide=False):

        """ Render to html """

        return self._html('Experiments', wide)


class Reference(object):

    """ Used for handling references.

    Instancses of this class are instantiated with a ES-DOC citation document,
    and return an instance which has two key attributes:

    .citestring: is a string to be used somewhere in a table, of the form
    author (year).

    .citeguess is a string to be used to provide information for using that
    citation in a bibliography.

    An additional attribute is also created:
    .text is also an attribute which is the best guess as to the full reference
    list item that can be generated from the content. Bibtex will do this better.

    As written this works well for tables which are to appear in latex documents
    which have bibliographies generated by bibtex.

    The current version of the es-doc citation is not a perfect match for
    bibtex, future versions will be, so in the meantime, this is a bit of a hack.

    """

    def __init__(self, doc):

        """ Intialise with a pyesdoc citation document """

        self.doc = doc
        if self.doc.doi:
            self._populate()
            self.populated = True
        else:
            self.populated = False

    def _populate(self):

        """ Want a citation string as opposed to a reference.
        That is, we want author (year), as opposed to
        author, title, journal, volume pages etc, they go
        in the bibliography."""

        # Assume the first word is what we want, and we can find well formed years
        # This sucks, but will work for these ones.
        # Roll on bibtex for citations in the CIM.

        citation_detail = self.doc.citation_detail
        author = citation_detail.split(',')[0]
        match = '([^\w])19|20\d\d([^\w])*?'
        m = re.search(match, citation_detail)
        if m:
            year = m.group(0)
        else:
            year = None

        # one error in existing es-doc content to be fixed:
        if 'van Vuuren DP' in author:
            author = 'van Vuuren'
            print 'applying vv fix'

        self.year = int(year)

        # We assume that this table will have entries which ne

        # I use the first three letters of a an authors name, and for
        # three or more authors, EA, and then the year for my bibtex citation string
        self.citeguess = author[0:3] + 'EA' + year[2:]
        # This is what will appear in the table:
        self.citestring = '%s et al. (%s)' % (author, year)
        # Keep this for a reference list for checking against the eventual bibtex reference list.
        self.text = citation_detail


class CMIP6(Doc):

    """ Need to hack about a bit with the CMIP6 class since
     we want suitable journal string citations, the actual
     matching reference list is generated from my zotero
     so there is a bit of manual work to make sure
      they are all there. But given we only use DOI
      references here, it's easy to get them in and out
      of zotero."""
    
    def __init__(self):
        """ Load the CMIP6 experiment description."""
        # simple header only necessary for this table of MIPs
        self.header = '<tr class="ename"><td colspan="1">{{d.name}} ({{mips}})</td></tr>'
        self.mips = 'core MIPS recorded by ES-DOC'
        self._settemplates(self.onecol, self.twocol)

        r = Repo()
        c = r.getbyname('CMIP6', 'mips')
        self.doc = c
        self.related = []

        # two properties to help the use of the resulting table in a paper
        self.reference_list = []
        # nocite list intended for cutting and pasting directly into a latex document!
        self.nocite = ''

        for m in c.sub_projects:
            mdoc = r.getbyname(m.name, 'mips')
            description = mdoc.long_name+' - '
            citations = []

            # for these purposees we only want the things with a doi
            # and we want only one, so we have to develop a heuristic to get the right one
            for ci in mdoc.citations:
                cidoc = esd.retrieve(ci.id)
                ref = Reference(cidoc)
                if ref.populated:
                    citations.append(ref)
            citations.sort(key=lambda cc: cc.year)
            index = -1
            if len(citations) > 1:
                # start by getting the most recent
                year = citations[-1].year
                index = -1
                for i in range(len(citations)-1):
                    if citations[i].year == year:
                        if m.name in citations[i].text:
                            # it's one of the most recent and it has the MIP name
                            # in the document title.
                            index = i
            description += citations[index].citestring
            self.reference_list.append(citations[index].text)
            self.nocite += '\\nocite{%s}\n' % citations[index].citeguess

            # overwrite the real description for the purpose of this table
            mdoc.description = description
            self.related.append(mdoc)

        # want alphabetical order
        self.related.sort(key=lambda mm:  mm.name)

    def html(self, wide=False):
        """ Render to html """
        return self._html('MIPs', wide)


class TestExperiment(unittest.TestCase):

    """ Unit tests which are not really tests, but showcase what the code can do"""

    def setUp(self):

        # this class provides the interface to the ES-DOC repoository
        repo = Repo()

        # We use G7SST1-cirrus as our exemplar experiment
        expdoc = repo.getbyname('G7SST1-cirrus')

        # we use the DECK as our exemplar MIP
        mipdoc = repo.getbyname('DECK', 'mip')

        # load the documents into the testcalss
        self.E = Experiment(expdoc)
        self.M = Mip(mipdoc)

        # and choose some meaningful output names
        # we choose these here so the individual methods can use them, and the
        # tear down can find them when we are done.
        self.testoutput = ['single.pdf', 'double.pdf', 'doubleMIP.pdf', 'refsCMIP.pdf']

    def testHTML(self):

        """ make sure the html output works """

        html = self.E.html()

    def testSingleExp(self):

        """ single column experiment """

        self.E.render(self.testoutput[0])

    def testDoubleExp(self):

        """ double column experiment """

        self.E.render(self.testoutput[1], wide=True)

    def testDoubleMIP(self):

        """ double column mip table """

        self.M.render(self.testoutput[2], wide=True)

    def testCMIP6(self):

        """ Create a table which names each of the CMIP experiments, adds references for
        each, and outputs the strings necessary for bibtex to put the references in the
        reference list."""

        c = CMIP6()
        c.render(self.testoutput[3])
        for r in c.reference_list:
            print r
        print c.nocite

    def NOtearDown(self):

        """ For example purposes, we do not remove the outputs,
        which is why this is NOtearDown. If you really want to
        use this for unit tests, rename to tearDown."""

        for f in self.testoutput:
            if os.path.exists(f):
                os.remove(f)

if __name__ == "__main__":
    unittest.main()
