import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By

class Scrape_Banks:
    def __init__(self):
        pass

    def scrape_article_titles(self, url):
        # Sending an HTTP request to the URL
        response = requests.get(url)

        # List to hold the text of each article
        article_texts = []

        # Checking if the request was successful
        if response.status_code == 200:
            # Parsing the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')

            # Finding article titles (assuming they are within <h2> tags)
            articles = soup.find_all('h2')

            # Extracting and printing article titles
            for i, article in enumerate(articles):
                print(f"{i}. {article.text}")
                article_texts.append(article.text)
        else:
            print("Failed to retrieve the webpage.")

        return article_texts

    def test_eight_components(self):
        driver = webdriver.Chrome()

        driver.get("https://www.selenium.dev/selenium/web/web-form.html")

        title = driver.title
        assert title == "Web form"

        driver.implicitly_wait(0.5)

        text_box = driver.find_element(by=By.NAME, value="my-text")
        submit_button = driver.find_element(by=By.CSS_SELECTOR, value="button")

        text_box.send_keys("Selenium")
        submit_button.click()

        message = driver.find_element(by=By.ID, value="message")
        value = message.text
        print(value)
        assert value == "Received!"

        #driver.quit()
        # Extracting and storing article text
