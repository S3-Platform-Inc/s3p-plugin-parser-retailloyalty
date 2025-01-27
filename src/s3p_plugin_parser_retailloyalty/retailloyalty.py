# import datetime
import time

from s3p_sdk.exceptions.parser import S3PPluginParserOutOfRestrictionException, S3PPluginParserFinish
from s3p_sdk.plugin.payloads.parsers import S3PParserBase
from s3p_sdk.types import S3PRefer, S3PDocument, S3PPlugin, S3PPluginRestrictions
from s3p_sdk.types.plugin_restrictions import FROM_DATE
from selenium.common import NoSuchElementException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from datetime import datetime

import dateparser


class RetailLoyalty(S3PParserBase):
    """
    A Parser payload that uses S3P Parser base class.
    """
    HOST = 'https://retail-loyalty.org/news/'
    url_template = f'{HOST}/research/index.htm?bis_fsi_publs_page='

    def __init__(self, refer: S3PRefer, plugin: S3PPlugin, restrictions: S3PPluginRestrictions, web_driver: WebDriver):
        super().__init__(refer, plugin, restrictions)

        # Тут должны быть инициализированы свойства, характерные для этого парсера. Например: WebDriver
        self._driver = web_driver
        self._wait = WebDriverWait(self._driver, timeout=20)

    def _parse(self):
        """
        Метод, занимающийся парсингом. Он добавляет в _content_document документы, которые получилось обработать
        :return:
        :rtype:
        """
        # HOST - это главная ссылка на источник, по которому будет "бегать" парсер
        self.logger.debug(F"Parser enter to {self.HOST}")

        # ========================================
        # Тут должен находится блок кода, отвечающий за парсинг конкретного источника
        # -
        for url in self._encounter_pages():
            # Получение новой страницы с новостями
            links = self._collect_doc_links(url)  # выборка всех ссылок на новости из страницы
            for link in links:
                self._parse_page(link)

    def _collect_doc_links(self, url) -> list:
        self._initial_access_source(url)
        self.logger.debug(f'Start collect publications from {url}')

        links = []

        try:
            news = self._driver.find_elements(By.CLASS_NAME, 'news-item')
            for new in news:
                text_block = WebDriverWait(new, 2).until(ec.presence_of_element_located((By.CLASS_NAME, 'text-block')))
                el = WebDriverWait(text_block, 2).until(ec.presence_of_element_located((By.XPATH, 'a[1]')))
                links.append(str(el.get_attribute('href')))
        except Exception as e:
            self.logger.error(e)

        return links

    def _encounter_pages(self) -> str:
        _base = "https://retail-loyalty.org/news/"
        _params = '?PAGEN_1='
        page = 1
        while True:
            url = _base + _params + str(page)
            page += 1
            yield url

    def _parse_page(self, url):
        self.logger.debug(f'Start parse news at {url}')

        try:
            self._initial_access_source(url, 4)

            _article = WebDriverWait(self._driver, 2).until(
                ec.presence_of_element_located((By.CLASS_NAME, 'news-article')))
            _title = WebDriverWait(_article, 2).until(
                ec.presence_of_element_located((By.CLASS_NAME, 'page-header'))).text
            _weblink = url
            _date = WebDriverWait(_article, 2).until(
                ec.presence_of_element_located((By.CLASS_NAME, 'news-line-date'))).text
            _time = WebDriverWait(_article, 2).until(
                ec.presence_of_element_located((By.CLASS_NAME, 'news-line-time'))).text

            _published = dateparser.parse(_date + _time)

        except Exception as e:
            raise NoSuchElementException(
                'Страница новости не открывается или ошибка получения обязательных полей') from e
        else:
            doc = S3PDocument(
                None,
                _title,
                None,
                None,
                _weblink,
                None,
                None,
                _published,
                None,
            )

            _text = WebDriverWait(_article, 2).until(ec.presence_of_element_located((By.ID, 'article'))).text
            doc.text = _text
            try:
                _abstract = WebDriverWait(_article, 2).until(
                    ec.presence_of_element_located((By.ID, 'news-line-preview'))).text
                doc.abstract = _abstract
            except:
                self.logger.debug('There aren\'t a abstract in the article')

            _others = {}
            try:
                _tag_el = _article.find_element(By.CLASS_NAME, 'line-tags')
                _tags = []
                for _tag in _tag_el.find_elements(By.CLASS_NAME, 'rubrics-name'):
                    _span = _tag.find_element(By.TAG_NAME, 'span')
                    _tags.append(_tag.text.replace(_span.text, ''))
                _others['tags'] = tuple(_tags)
            except:
                self.logger.debug('There aren\'t a tags in the article')

            try:
                _rubric_els = _article.find_element(By.CLASS_NAME, 'line-rubrics')
                _rubrics = []
                for _rubric in _rubric_els.find_elements(By.CLASS_NAME, 'rubrics-name'):
                    _span = _rubric.find_element(By.TAG_NAME, 'span')
                    _rubrics.append(_rubric.text.replace(_span.text, ''))
                _others['rubrics'] = tuple(_rubrics)
            except:
                self.logger.debug('There aren\'t a rubrics in the article')

            doc.other_data = _others

            try:
                self._find(doc)
            except S3PPluginParserOutOfRestrictionException as e:
                if e.restriction == FROM_DATE:
                    self.logger.debug(f'Document is out of date range `{self._restriction.from_date}`')
                    raise S3PPluginParserFinish(self._plugin,
                                                f'Document is out of date range `{self._restriction.from_date}`',
                                                e)

    def _initial_access_source(self, url: str, delay: int = 2):
        self._driver.get(url)
        self.logger.debug('Entered on web page ' + url)
        time.sleep(delay)
        self._agree_cookie_pass()

    def _agree_cookie_pass(self):
        """
        Метод прожимает кнопку agree на модальном окне
        """
        cookie_agree_xpath = '//*[@id="onetrust-accept-btn-handler"]'

        try:
            cookie_button = self._driver.find_element(By.XPATH, cookie_agree_xpath)
            if WebDriverWait(self._driver, 5).until(ec.element_to_be_clickable(cookie_button)):
                cookie_button.click()
                self.logger.debug(F"Parser pass cookie modal on page: {self._driver.current_url}")
        except NoSuchElementException as e:
            self.logger.debug(f'modal agree not found on page: {self._driver.current_url}')
