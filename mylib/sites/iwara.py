#!/usr/bin/env python3
from abc import ABCMeta
from urllib.parse import urlparse, urlunparse

import youtube_dl.extractor.iwara as ytdl_iwara

from mylib import easy
from mylib.easy import text
from mylib.ex import html
from mylib.web_client import get_html_element_tree

HE = html.lxml_html.HtmlElement

regex = easy.re


def find_url_in_text(s: str) -> list:
    prefix = 'https://iwara.tv'
    pattern = '/videos/[0-9a-zA-Z]+'
    urls = [prefix + e for e in text.regex_find(pattern, s, dedup=True) if 'thumbnail' not in e]
    return urls


# ytdl_iwara.InfoExtractor = youtube_dl_x.ytdl_common.InfoExtractor  # SEEMINGLY NO EFFECT


class IwaraIE(ytdl_iwara.IwaraIE, metaclass=ABCMeta):
    def _real_extract(self, url):
        data = super()._real_extract(url)
        # youtube_dl_x.safe_title(data)
        try:
            html = get_html_element_tree(url)
            uploader = html.xpath('//div[@class="node-info"]//div[@class="submitted"]//a[@class="username"]')[0].text
            data['uploader'] = uploader
            # print('#', 'uploader:', uploader)
        except IndexError:
            pass
        return data


def iter_all_video_url_of_user(who: str, ecchi=True, only_urls=False):
    m = regex.match(r'.*iwara\.tv/users/(.+)/?', who)
    if m:
        who = m.group(1)
    domain = 'ecchi.iwara.tv' if ecchi else 'iwara.tv'
    url = f'https://{domain}/users/{who}/videos?language=en'
    end = False

    while not end:
        r = easy.call_factory_retry(html.rq.get)(url)
        h = html.HTMLResponseParser(r).check_ok_or_raise().get_html_element()
        for e in h.cssselect('.field-item a'):
            href = e.attrib['href']
            img_d = e.find('img').attrib
            thumbnail = img_d['src']
            title = img_d['title']
            url = f'https://{domain}{href}'
            url_pr = urlparse(url)
            url = urlunparse((url_pr.scheme, url_pr.netloc, url_pr.path, '', '', ''))
            if only_urls:
                yield url
            else:
                yield {'title': title, 'url': url, 'thumbnail': thumbnail}
        find_next = h.cssselect('.pager-next a')
        if find_next:
            go_next = find_next[-1]
            url = f'https://{domain}{go_next.attrib["href"]}'
        else:
            end = True


def find_video_id_in_link(link: str):
    return regex.match(r'.*/videos/([0-9a-z]+)', link).group(1)
