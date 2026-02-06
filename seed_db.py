import boto3
import json
import uuid
from decimal import Decimal

# AWS Configuration
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('Books')

# Load your local JSON file
with open('books.json', 'r') as f:
    books = json.load(f, parse_float=Decimal) # DynamoDB requires Decimal for floats

print("📦 Starting upload to DynamoDB...")

for book in books:
    # Generate a string ID if it's currently an integer (1, 2, 3...)
    # or keep it if you want to stick to simple IDs for now.
    # For a cloud app, string IDs are safer, so let's convert.
    book['id'] = str(book['id']) 
    
    # Upload to DynamoDB
    table.put_item(Item=book)
    print(f"✅ Uploaded: {book['title']}")

print("🎉 Import Complete!")