# Weaviate Site Search

## Running the project locally

### Step 1 – Clone the weaviate-io project
The import job, builds chunks straight from the weaviate-io markdown. The project needs to be present locally.

If you don't have the weaviate-io project yet, clone it from [https://github.com/weaviate/weaviate-io](https://github.com/weaviate/weaviate-io).

For example:
```
git clone --depth 1 https://github.com/weaviate/weaviate-io.git
```

If you already have the weaviate-io project, make sure to pull the latest info before you run the import task.


### Step 2 – Run the import

To run the import task locally, you need to provide 3 arg params:
1. full path to the local weaviate-io folder (from step 1)
2. path to the docs - by default this is `/developers/weaviate`
3. path to the blog - by default this is `/blog`

And call it like this:
```
python import.py /Users/sebawita/github/weaviate-io /developers/weaviate /blog
```


## How to setup the python environment with venv
To run the project locally, it is best to setup python environment with venv.

### Setup – do this only once
First create a new venv configuration.
```
python3 -m venv .venv
```

Then switch to the new configuration:
```
source .venv/bin/activate
```

And install the required packages.
```
pip install -r requirements.txt
```

### Activate
If in the future, you need to switch to the venv setup, just call:
```
source .venv/bin/activate
```

### Deactivate
To disconnect from the venv environment, call:
```
source deactivate
```

### Updating requirements.txt

If the installed packages change. Update requirements.txt by calling:
```
pip freeze > requirements.txt
```
