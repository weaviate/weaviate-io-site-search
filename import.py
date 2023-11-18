import re
import marko
import os
import sys
import weaviate
from bs4 import BeautifulSoup

WCS_HOST = os.environ['WCS_HOST']
WCS_KEY = os.environ['WCS_KEY']
OPENAI_APIKEY = os.environ['OPENAI_APIKEY']

def replace_url_to_link(s):
    s = re.sub(r'[^a-zA-Z0-9_ ]', '', s)
    return s.lower().replace(' ', '-')


def find_all(sub, a_string):
    result = []
    k = 0
    while k < len(a_string):
        k = a_string.find(sub, k)
        if k == -1:
            return result
        else:
            result.append(k)
            k += 1 #change to k += len(sub) to not search overlapping results
    return result


def find_between_keys(html, start, stop):
    start_stop_string = ''
    i = 0
    for letter in html:
        if i < start:
            i += 1
            continue
        start_stop_string += letter
        if i == stop:
            break
        i += 1
    return start_stop_string


def find_and_remove_includes(s):
    start = s.find('{%') + len('%}')
    end = s.find('%}')
    substring = s[start:end]
    if start > 1:
        s = find_and_remove_includes(s.replace('{%' + substring + '%}', ' '))
    return s


def parse_titles_and_content(html, mdf, path):

    # find the doc title
    findIntroArray = html.split("\n")
    doc_title = ''
    url = parse_url(mdf, path)
    for l in findIntroArray:
        if contains_title(l):
            doc_title = get_title(l)
        # Update url if slug provided
        elif l.startswith('slug'):
            if '/blog/' in mdf:
                url = '/blog/' + l.replace('slug: ', '').replace(' ', '', 100)

    # split the headers
    content_array = []
    header_positions = find_all('<h', html)
    i = 2
    while i < len(header_positions)-1:
        content = find_between_keys(html, header_positions[i], header_positions[i+1])
        soup = BeautifulSoup(content[:-1], "html.parser")
        title = soup.find_all(re.compile('^h[1-6]$'))
        if len(title) > 0:
            content_array.append({
                'title': title[0].get_text(),
                'url': url,
                'anchor': replace_url_to_link(title[0].get_text()),
                'content': find_and_remove_includes(soup.get_text().replace(title[0].get_text(), '').replace('\n', ' ')).strip(),
                'order': i,
                'pageTitle': doc_title
            })
        i += 1
    return content_array


def open_markdown_file(mdf, path):
    with open(mdf, "r") as md:
        page_content_array = parse_titles_and_content(marko.convert(md.read()), mdf, path)
        return page_content_array


def create_weaviate_schema(client):

    client.schema.delete_all()

    class_obj = {
        "class": "PageChunkOpenAI",
        "description": "A chunk of a page with potential answers",
        "moduleConfig": {
            "text2vec-openai": {
                "model": "ada",
                "modelVersion": "002",
                "type": "text"
            }
        },
        "properties": [
            {
                "dataType": [
                    "string"
                ],
                "description": "Title of the chunk",
                "name": "title",
                "moduleConfig": {
                    "text2vec-openai": {
                        "skip": False,
                        "vectorizePropertyName": False
                    }
                }
            },
            {
                "dataType": [
                    "string"
                ],
                "description": "Anchor of the chunk on the page",
                "name": "anchor",
                "moduleConfig": {
                    "text2vec-openai": {
                        "skip": True,
                        "vectorizePropertyName": False
                    }
                }
            },
            {
                "dataType": [
                    "string"
                ],
                "description": "Url of the page",
                "name": "url",
                "moduleConfig": {
                    "text2vec-openai": {
                        "skip": True,
                        "vectorizePropertyName": False
                    }
                }
            },
            {
                "dataType": [
                    "string"
                ],
                "description": "Type of the item",
                "name": "typeOfItem",
                "moduleConfig": {
                    "text2vec-openai": {
                        "skip": True,
                        "vectorizePropertyName": False
                    }
                }
            },
            {
                "dataType": [
                    "text"
                ],
                "description": "The content of the chunk",
                "name": "content",
                "moduleConfig": {
                    "text2vec-openai": {
                        "skip": False,
                        "vectorizePropertyName": False
                    }
                }
            },
            {
                "dataType": [
                    "int"
                ],
                "description": "Order of the item on the page",
                "name": "order",
                "moduleConfig": {
                    "text2vec-openai": {
                        "skip": True,
                        "vectorizePropertyName": False
                    }
                }
            },
            {
                "dataType": [
                    "string"
                ],
                "description": "Title of the page",
                "name": "pageTitle",
                "moduleConfig": {
                    "text2vec-openai": {
                        "skip": True,
                        "vectorizePropertyName": False
                    }
                }
            },
        ]
    }

    client.schema.create_class(class_obj)

def skip_hidden(file, dir):
    return file.startswith('_') or re.search(r'/_', subdir) is not None

def is_markdown(file):
    return re.search(r'\.mdx?$', file) is not None

def contains_title(line):
    return re.search('title:', line) is not None
def get_title(line):
    return re.search('title: (.*)', line).group(1)

def parse_url(mdf, path):
    return (
        mdf
        .replace('.mdx', '.md')
        .replace('/index.md', '')
        .replace('.md', '')
        .replace(path, '')
        .replace('./', '/')
    )

if __name__ == "__main__":

    try:
        rootdir = sys.argv[1]
        docsdir = sys.argv[2]
        blogdir = sys.argv[3]
        if os.path.exists(rootdir) == False or os.path.exists(rootdir + docsdir) == False or os.path.exists(rootdir + blogdir) == False:
            raise Exception()
    except:
        print('This paths don\'t exist')
        exit(1)

    try:
        auth_config = weaviate.AuthApiKey(api_key=WCS_KEY)

        client = weaviate.Client(
            url=WCS_HOST,
            auth_client_secret=auth_config,
            timeout_config=600,
            additional_headers={
                "X-OpenAI-Api-Key": OPENAI_APIKEY
            }
        )

        client.batch.configure(
            timeout_retries=3,
            batch_size=100, 
            dynamic=False,
        )

        create_weaviate_schema(client)
    except:
        print("Can't reach VM for Weaviate, continue without updating search")
        exit(0)

    c = 0

    print('Start import')

    # Add docs
    with client.batch as batch:
        for subdir, dirs, files in os.walk(rootdir + docsdir):
            for file in files:
                if skip_hidden(file, subdir):
                    continue;
                if is_markdown(file):
                    parsed = open_markdown_file(os.path.join(subdir, file), rootdir)
                    c += len(parsed)
                    for chunk in parsed:
                        chunk['typeOfItem']='docs'
                        batch.add_data_object(chunk, 'PageChunkOpenAI')

    # Add blogs
    with client.batch as batch:
        for subdir, dirs, files in os.walk(rootdir + blogdir):
            for file in files:
                if skip_hidden(file, subdir):
                    continue;
                if is_markdown(file):
                    parsed = open_markdown_file(os.path.join(subdir, file), rootdir)
                    c += len(parsed)
                    for chunk in parsed:
                        chunk['typeOfItem']='blog'
                        batch.add_data_object(chunk, 'PageChunkOpenAI')

    print('Done', c)
