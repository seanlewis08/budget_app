# Importing required libraries
import requests
from bs4 import BeautifulSoup

# Function to scrape article titles
def scrape_article_titles(url):
    # Sending an HTTP request to the URL
    response = requests.get(url)
    
    # Checking if the request was successful
    if response.status_code == 200:
        # Parsing the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Finding article titles (assuming they are within <h2> tags)
        articles = soup.find_all('h2')
        
        # Extracting and printing article titles
        for i, article in enumerate(articles):
            print(f"{i+1}. {article.text}")
    else:
        print("Failed to retrieve the webpage.")

# URL of the news website (replace with actual URL)
url = "https://www.example.com/news"

# Calling the function
scrape_article_titles(url)
