import re
import marko
import os
import sys
import weaviate
from weaviate.classes.init import AdditionalConfig, Timeout
from bs4 import BeautifulSoup
from tqdm import tqdm

WCD_URL = os.environ['WEAVIATE_SEARCH_URL']
WCD_KEY = os.environ['WEAVIATE_SEARCH_KEY_WRITE']

def connect_to_weaviate():
    print("> INFO: Connecting to WCS")
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=WCD_URL,
        auth_credentials=weaviate.auth.AuthApiKey(WCD_KEY),
        # headers={
        #     "X-OpenAI-Api-Key": os.getenv("WEAVIATE_IO_OPENAI_KEY")
        # },
        additional_config=AdditionalConfig(
            timeout=Timeout(init=30, query=60, insert=600)  # Values in seconds
        )
    )

    print("> INFO: client.is_ready() >> ", client.is_ready())
    
    return client

def recreate_chunk_collection(client):
    from weaviate.classes.config import Configure
    from weaviate.classes.config import Property, DataType

    print("> INFO: Recreating PageChunk collection")

    if(client.collections.exists("PageChunk")):
        client.collections.delete("PageChunk")

    client.collections.create(
        name="PageChunk",
        vectorizer_config=Configure.Vectorizer.text2vec_openai(
            # model="ada",
            # model_version="002"
            model="text-embedding-3-small"
        ),

        properties=[
            Property(name="title", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="anchor", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="url", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="typeOfItem", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="order", data_type=DataType.INT, skip_vectorization=True),
            Property(name="pageTitle", data_type=DataType.TEXT, skip_vectorization=True),
        ]
    )

    print("> INFO: Recreating PageChunk collection > DONE")

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

    # find title
    for l in findIntroArray:
        # keep checking for title until it is found
        if (contains_title(l)):
            doc_title = get_title(l)
            break

    # find blog url if slug provided
    if '/blog/' in mdf:
        for l in findIntroArray:
            if l.startswith('slug'):
                url = '/blog/' + l.replace('slug: ', '').replace(' ', '', 100)
                break

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


def skip_hidden(file, subdir):
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

def list_files(resource_dir):
    file_list = []
    for subdir, dirs, files in os.walk(rootdir + resource_dir):
        for file in files:
            if skip_hidden(file, subdir):
                continue;
            if is_markdown(file):
                file_list.append(os.path.join(subdir, file))
    return file_list

if __name__ == "__main__":

    try:
        rootdir = sys.argv[1]
        docsdir = sys.argv[2]
        blogdir = sys.argv[3]
        if os.path.exists(rootdir) == False or os.path.exists(rootdir + docsdir) == False or os.path.exists(rootdir + blogdir) == False:
            raise Exception()
    except:
        print(">> ERROR >> This paths don't exist. Check args passed to import.")
        exit(1)

    try:
        client = connect_to_weaviate()
        recreate_chunk_collection(client)
    except:
        print(">> ERROR >> Can't reach VM for Weaviate, continue without updating search")
        exit(1)

    counter = 0

    print("> INFO: Start import")

    chunk_collection = client.collections.get("PageChunk")

    # Add docs
    print("> INFO: Import DOCS")
    doc_files = list_files(docsdir)
    with chunk_collection.batch.fixed_size(500, 1) as batch:
        for file in tqdm(doc_files):
            parsed = open_markdown_file(file, rootdir)
            counter += len(parsed)

            for chunk in parsed:
                chunk['typeOfItem']='docs'
                batch.add_object(properties=chunk)

            if batch.number_errors > 20:
                print(">>> ERROR >>> Too many errors (", batch.number_errors ,") during batch import for [docs]. Import aborted.")
                break
    
    # we can accept a few errors
    if(batch.number_errors > 0):
        print(">>> ERROR >>> There were some errors (", len(chunk_collection.batch.failed_objects) ,") during batch import for [docs]. Printing the first 3.")
        for err in chunk_collection.batch.failed_objects[:3]:
            print(err.object_)
            print(err.message, "\n")

    # Add blogs
    print("> INFO: Import BLOGS")
    blog_files = list_files(blogdir)
    with chunk_collection.batch.fixed_size(500, 1) as batch:
        for file in tqdm(blog_files):
            parsed = open_markdown_file(file, rootdir)
            counter += len(parsed)

            for chunk in parsed:
                chunk['typeOfItem']='blog'
                batch.add_object(properties=chunk)

            if batch.number_errors > 20:
                print(">>> ERROR >>> Too many errors (", batch.number_errors ,") during batch import for [blogs]. Import aborted.")
                break
    
    # we can accept a few errors
    if(batch.number_errors > 0):
        print(">>> ERROR >>> There were some errors (", len(chunk_collection.batch.failed_objects) ,") during batch import for [blogs]. Printing the first 3.")
        for err in chunk_collection.batch.failed_objects[:3]:
            print(err.object_)
            print(err.message, "\n")

    print(f"> INFO: Done. Imported {counter} chunks")
    client.close()