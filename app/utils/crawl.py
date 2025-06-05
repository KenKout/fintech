import httpx
import html2text
import re
import json
from loguru import logger
from enum import Enum
from bs4 import BeautifulSoup
from openai import OpenAI
from app.envs import settings
from app.utils.prompt import SYSTEMP_PROMPT_PARSE

class VBPLSection(Enum):
    """
    Enum representing different sections of a legal document.
    """
    CHAPTER = "Chương"
    SECTION = "Mục"
    ARTICLE = "Điều"
    CLAUSE = "Khoản"
    POINT = "Điểm"
    SUBPOINT = "Mục con"
    
class VBPLCrawler:
    """
    A class to crawl and parse legal documents from the Vietnam Government Portal (VBPL).
    """
    def __init__(self):
        self.toanvan_url = "https://vbpl.vn/nganhangnhanuoc/Pages/vbpq-toanvan.aspx?ItemID={}"
        self.luocdo_url = "https://vbpl.vn/nganhangnhanuoc/Pages/vbpq-luocdo.aspx?ItemID={}"

        self.openai_client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )

    def crawl_toanvan(self, id: str) -> str:
        """
        Crawls the given URL and returns the HTML content as a string.

        Args:
            url (str): The URL to crawl toanvan page.

        Returns:
            str: The HTML content of the page.
        """
        try:
            response = httpx.get(self.toanvan_url.format(id), timeout=30)
            response.raise_for_status()  # Raise an error for bad responses
            return response.text
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            return ""
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            return ""
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return ""
    
    def crawl_luocdo(self, id: str) -> str:
        """
        Crawls the given URL and returns the HTML content as a string.

        Args:
            url (str): The URL to crawl luocdo page.

        Returns:
            str: The HTML content of the page.
        """
        try:
            response = httpx.get(self.luocdo_url.format(id), timeout=30)
            response.raise_for_status()  # Raise an error for bad responses
            return response.text
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            return ""
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            return ""
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return ""
        
    def parse_html(self, html: str) -> BeautifulSoup:
        """
        Parses the given HTML content and returns a BeautifulSoup object.

        Args:
            html (str): The HTML content to parse.

        Returns:
            BeautifulSoup: A BeautifulSoup object representing the parsed HTML.
        """
        return BeautifulSoup(html, 'html.parser')
    
    def extract_toanvancontent(self, soup: BeautifulSoup) -> str:
        """
        Extracts the full text from the parsed HTML soup.

        Args:
            soup (BeautifulSoup): The BeautifulSoup object containing the parsed HTML.

        Returns:
            str: The plain text extracted from the fulltext div.
        """
        fulltext_div = soup.find('div', class_='toanvancontent')
        if fulltext_div:
            text_maker = html2text.HTML2Text()
            text_maker.ignore_links = True
            text_maker.ignore_images = True
            return text_maker.handle(str(fulltext_div)).strip()
        return ""
    
    def extract_info(self, soup: BeautifulSoup) -> dict:
        """
        Extracts document information from the parsed HTML soup.

        Args:
            soup (BeautifulSoup): The BeautifulSoup object containing the parsed HTML.

        Returns:
            dict: A dictionary containing the document information.
        """
        info = {}

        vbInfo_div = soup.find('div', class_='vbInfo')
        if vbInfo_div:
            text_maker = html2text.HTML2Text()
            text_maker.ignore_links = True
            text_maker.ignore_images = True
            plain_text = text_maker.handle(str(vbInfo_div)).strip()
            lines = plain_text.split('\n')
            for line in lines:
                if "Hiệu lực: " in line:
                    info["document_status"] = line.split("Hiệu lực: ")[-1].strip()
                elif "Ngày có hiệu lực: " in line:
                    info["effective_date"] = line.split("Ngày có hiệu lực: ")[-1].strip()
                elif "Ngày hết hiệu lực: " in line:
                    info["expired_date"] = line.split("Ngày hết hiệu lực: ")[-1].strip()
                else:
                    pass
        
        boxmap_div = soup.find('div', class_='box-map')
        if boxmap_div:
            text_maker = html2text.HTML2Text()
            text_maker.ignore_links = True
            text_maker.ignore_images = True
            plain_text = text_maker.handle(str(boxmap_div)).strip()
            lines = plain_text.split('\n')
            info["document_title"] = lines[-1].replace('*', '').strip() if lines else ""

        header_div = soup.find('div', class_='header')
        if header_div:
            a_tag = header_div.find('a')
            if a_tag and 'href' in a_tag.attrs:
                info["document_id"] = a_tag['href'].split('ItemID=')[-1].split('&')[0].strip()
        
        relationship = {}
        html_luocdo = self.crawl_luocdo(info.get("document_id", "")) if info.get("document_id") else ""
        if html_luocdo:
            soup_luocdo = self.parse_html(html_luocdo)
            luocdo_div = soup_luocdo.find('div', class_='vbLuocDo')
            relationship = {}
            
            if luocdo_div:
                luocdo_children = luocdo_div.select('div[class^="luocdo"]')
                for child in luocdo_children:
                    # Get the title
                    child_title = child.find('div', class_='title') or child.find('div', class_='titleht')
                    if child_title:
                        # Extract the title text properly
                        title_text = ""
                        title_links = child_title.find_all('a')
                        for link in title_links:
                            if link.get('class') and 'openClose' in link.get('class'):
                                continue
                            title_link_text = link.get_text(strip=True)
                            if title_link_text:
                                title_text = title_link_text
                                break
                        
                        if title_text:
                            relationship[title_text] = []
                            
                            # Process content
                            content_div = child.find('div', class_='content')
                            if content_div:
                                list_items = content_div.find_all('li')
                                for li in list_items:
                                    # Extract just the main text, exclude child links
                                    main_text = ""
                                    for item in li.contents:
                                        if isinstance(item, str):
                                            main_text += item.strip()
                                        elif item.name == 'a' and 'jTips' in item.get('class', []):
                                            main_text += item.get_text(strip=True)
                                            href = item.get('href', '')
                                            if 'ItemID=' in href:
                                                item_id = href.split('ItemID=')[-1]
                                            else:
                                                item_id = info.get("document_id", "") if title_text == "Văn bản hiện thời" else ""
                                            
                                    if main_text:
                                        cleaned_text = re.sub(r'\s+', ' ', main_text).strip()
                                        append_data = {
                                            "title": cleaned_text,
                                            "id": item_id
                                        }
                                        relationship[title_text].append(append_data)

            info["relationship"] = relationship

        return info
    
    def parse_llm(self, id: str) -> dict:
        """
        Parses the content using OpenAI's LLM to extract relevant information.
        
        Args:
            id (str): The ID of the legal document to parse.

        Returns:
            dict: A dictionary containing the parsed information.
        """
        html_content = self.crawl_toanvan(id)
        if not html_content:
            return {}
        soup = self.parse_html(html_content)
        # content = self.extract_toanvancontent(soup)
        content = soup.find('div', class_='toanvancontent').get_text(strip=False)
        if not content:
            return {}
        
        content = content.splitlines()
        modified_lines = []
        for i, line in enumerate(content):
            modified_lines.append(f'{i+1} | {line.strip()}')

        modified_content = "\n".join(modified_lines)

        response = self.openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEMP_PROMPT_PARSE},
                {"role": "user", "content": modified_content}
            ],
            temperature=0.8,

        )
        response_text = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()

        try:
            response_json = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding error: {e}")
            logger.error(f"Response text: {response_text}")
            return {}
        
        for data in response_json:
            if data.get("type") == "ARTICLE":
                data["content"] = '\n'.join(content[data["start_line"]-1:data["end_line"]]).strip()
                del data["start_line"]
                del data["end_line"]
            else:
                children = data.get("children", [])
                for child in children:
                    if child.get("type") == "ARTICLE":
                        child["content"] = '\n'.join(content[child["start_line"]-1:child["end_line"]]).strip()
                        del child["start_line"]
                        del child["end_line"]
                    else:
                        for sub_child in child.get("children", []):
                            if sub_child.get("type") == "ARTICLE":
                                sub_child["content"] = '\n'.join(content[sub_child["start_line"]-1:sub_child["end_line"]]).strip()
                                del sub_child["start_line"]
                                del sub_child["end_line"]
        
        return {
            "data": response_json,
        }

    def parse(self, id: str) -> dict:
        """
        Parses the content and extracts relevant information.

        Args:
            id (str): The ID of the legal document to parse.

        Returns:
            dict: A dictionary containing the parsed information. Example structure:
                dict_result = {
                    "document_info": {
                        "document_id": "", # Mã số văn bản
                        "document_title": "", # Tiêu đề văn bản
                        "document_date": "", # Ngày ban hành
                        "document_status": "",
                        "effective_date": "",
                        "expired_date": ""
                    },
                    "data": [
                        {
                            "type": VBPLSection.CHAPTER,
                            "id_text": "",
                            "title": "",
                            "children": []
                        }
                    ]
                }
        """
        html_content = self.crawl_toanvan(id)
        if not html_content:
            return {}
        soup = self.parse_html(html_content)
        # content = self.extract_toanvancontent(soup)
        content = soup.find('div', class_='toanvancontent').get_text(strip=False)
        if not content:
            return {}

        with open('content.txt', 'w', encoding='utf-8') as f:
            f.write(content)

        # Clean up the content
        data = []
        title_regex = re.compile(r'([\s\S]+?)(?=(\n+\s*Điều\s*[0-9]+)|(\n+\s*Mục\s*[0-9]+))', re.IGNORECASE)
        chuong_regex = re.compile(r'\n*\s*(Chương\s*([MDCLXVI]+))\s*([\s\S]*?)(?=(\n+\s*Chương\s*([MDCLXVI]+))|\Z)')
        muc_regex = re.compile(r'\n*\s*(Mục\s*[0-9]+)([\s\S]+?)(?=(\n+\s*Mục\s*[0-9]+)|(\n+\s*Chương\s*([MDCLXVI]+))|\Z)')
        dieu_regex = re.compile(r'\n*\s*(Điều\s*[0-9]*\\*\.+[\s\S]+?)(?=\n+\s*Điều\s*[0-9]+\\*\.|\Z)')

        chuong_matches = chuong_regex.findall(content)
        if chuong_matches:
            for chuong in chuong_matches:
                chuong_data = {
                    "type": VBPLSection.CHAPTER.name,
                    "id_text": chuong[0].strip(),
                    "title": "",
                    "children": []
                }
                
                title_match = title_regex.search(chuong[2])
                if title_match:
                    chuong_data["title"] = re.sub(r'\s+', ' ', re.sub(r'[#*_\[\]\(\)-]', '', title_match.group(0))).strip()
                    chuong_content = chuong[2].replace(chuong_data["title"], "").strip()
                else:
                    chuong_data["title"] = ""
                    chuong_content = chuong[2].strip()

                muc_matches = muc_regex.findall(chuong_content)
                if muc_matches:
                    for muc in muc_matches:
                        muc_data = {
                            "type": VBPLSection.SECTION.name,
                            "id_text": muc[0].strip(),
                            "title": "",
                            "children": []
                        }
                        
                        title_match = title_regex.search(muc[1])
                        if title_match:
                            muc_data["title"] = re.sub(r'\s+', ' ', re.sub(r'[#*_\[\]\(\)-]', '', title_match.group(0))).strip()
                            muc_content = muc[1].replace(muc_data["title"], "").strip()
                        else:
                            muc_data["title"] = ""
                            muc_content = muc[1].strip()

                        dieu_matches = dieu_regex.findall(muc_content)

                        for dieu in dieu_matches:
                            dieu_data = {
                                "type": VBPLSection.ARTICLE.name,
                                "content": dieu.replace('*', '').strip(),
                            }
                            muc_data["children"].append(dieu_data)

                        chuong_data["children"].append(muc_data)
                        
                    data.append(chuong_data)
                else:
                    dieu_matches = dieu_regex.findall(chuong_content)
                    if dieu_matches:
                        for dieu in dieu_matches:
                            dieu_data = {
                                "type": VBPLSection.ARTICLE.name,
                                "content": dieu.replace('*', '').strip(),
                            }
                            chuong_data["children"].append(dieu_data)
                    data.append(chuong_data)
        else:
            muc_matches = muc_regex.findall(content)
            if muc_matches:
                for muc in muc_matches:
                    muc_data = {
                        "type": VBPLSection.SECTION.name,
                        "id_text": muc[0].strip(),
                        "title": "",
                        "children": []
                    }
                    
                    title_match = title_regex.search(muc[1])
                    if title_match:
                        muc_data["title"] = re.sub(r'\s+', ' ', re.sub(r'[#*_\[\]\(\)-]', '', title_match.group(0))).strip()
                        muc_content = muc[1].replace(muc_data["title"], "").strip()
                    else:
                        muc_data["title"] = ""
                        muc_content = muc[1].strip()

                    dieu_matches = dieu_regex.findall(muc_content)

                    for dieu in dieu_matches:
                        dieu_data = {
                            "type": VBPLSection.ARTICLE.name,
                            "content": dieu.replace('*', '').strip(),
                        }
                        muc_data["children"].append(dieu_data)

                    data.append(muc_data)
            else:
                # Check dieu
                dieu_matches = dieu_regex.findall(content)
                if dieu_matches:
                    for dieu in dieu_matches:
                        dieu_data = {
                            "type": VBPLSection.ARTICLE.name,
                            "content": dieu.replace('*', '').strip(),
                        }
                        data.append(dieu_data)

        # Create the final result dictionary
        info = self.extract_info(soup)
        dict_result = {
            "document_info": {
                "document_id": info.get("document_id", ""),
                "document_title": info.get("document_title", ""),
                "document_date": info.get("document_date", ""),
                "document_status": info.get("document_status", ""),
                "effective_date": info.get("effective_date", ""),
                "expired_date": info.get("expired_date", ""),
                "relationship": info.get("relationship", {})
            },
            "data": data
        }
        return dict_result
