import itertools
import re
import urllib.parse

from .common import InfoExtractor
from .youtube import YoutubeIE
from ..utils import (
    ExtractorError,
    clean_html,
    determine_ext,
    extract_attributes,
    get_element_by_class,
    get_element_by_id,
    get_element_html_by_class,
    get_element_html_by_id,
    get_elements_html_by_class,
    int_or_none,
    parse_qs,
    unified_strdate,
    urlencode_postdata,
    urljoin,
)
from ..utils.traversal import traverse_obj


class CreatsubIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?creatsub\.io/post/(?P<id>[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12})(?:[/?#-]|$)'
    _TESTS = [{
        'url': 'https://creatsub.io/post/2e277678-224a-43ee-bca1-8905016b1beb-jarda_dusek_cte_knihu_genov_kle',
        'info_dict': {
            'id': '2e277678-224a-43ee-bca1-8905016b1beb',
            'ext': 'm4a',
            'title': 'Jarda Dušek čte knihu GENOVÉ KLÍČE',
            'description': 'md5:5f00702969e7d484cb885c61242604c0',
            'uploader': 'Genové klíče',
            'uploader_id': 'genove-klice',
            'uploader_url': 'https://creatsub.io/genove-klice',
            'channel': 'Genové klíče',
            'upload_date': '20250318',
            'thumbnail': r're:https://creatsub\.io/post-data/2e277678-224a-43ee-bca1-8905016b1beb/.+\.webp',
            'like_count': int,
        },
    }, {
        'url': 'https://creatsub.io/post/2e277678-224a-43ee-bca1-8905016b1beb',
        'only_matching': True,
    }]

    def _real_extract(self, url):
        post_id = self._match_id(url)
        webpage, urlh = self._download_webpage_handle(url, post_id)
        if post_id in parse_qs(urlh.url).get('postId', []):
            self.raise_login_required('This post is locked', method='cookies')

        card = get_element_html_by_class('card', webpage) or webpage
        if get_element_by_class('bi-lock-fill', card) is not None:
            self.raise_login_required('This post is locked', method='cookies')

        author = get_element_html_by_class('fw-bold', card) or ''
        uploader = clean_html(author) or self._html_search_meta('article:author', webpage, default=None)
        uploader_url = urljoin(url, extract_attributes(author).get('href'))
        thumbnails = []
        for image in re.findall(r'<img\b[^>]*>', card):
            attributes = extract_attributes(image)
            image_url = urljoin(url, attributes.get('src'))
            if not image_url or 'rounded-circle' in attributes.get('class', '').split():
                continue
            if image_url not in {t['url'] for t in thumbnails}:
                thumbnails.append({'url': image_url})

        title = clean_html(get_element_by_class('card-title', card)) or self._og_search_title(webpage)
        post_url = self._og_search_url(webpage, default=None) or urlh.url
        description = (clean_html(get_element_by_class('card-text', card)) or '').replace('\ufeff', '')
        info = {
            'id': post_id,
            'title': title,
            'description': f'# {title}\n\n- {post_url}\n\n{description}',
            'webpage_url': post_url,
            'uploader': uploader,
            'uploader_id': urllib.parse.urlparse(uploader_url).path.strip('/') if uploader_url else None,
            'uploader_url': uploader_url,
            'channel': uploader,
            'upload_date': unified_strdate(clean_html(get_element_by_class('card-text-author', card))),
            'thumbnails': thumbnails,
            'like_count': int_or_none(get_element_by_class(f'totalCountLike-{post_id}', card)),
            'http_headers': {'Referer': url},
        }

        entries = []
        for media in re.finditer(r'(?s)<(?P<type>video|audio)\b[^>]*>.*?</(?P=type)>', card):
            attributes = extract_attributes(media[0])
            media_url = urljoin(url, attributes.get('data-playlist-url') or attributes.get('src'))
            if media_url and (
                    parse_qs(media_url).get('playlist') == ['true'] or determine_ext(media_url) == 'm3u8'):
                formats, subtitles = self._extract_m3u8_formats_and_subtitles(
                    media_url, post_id, 'mp4', m3u8_id='hls', headers=info['http_headers'])
                entry = {'formats': formats, 'subtitles': subtitles}
            else:
                entry = next(iter(self._parse_html5_media_entries(url, media[0], post_id)), None)
            if not entry:
                continue
            if media['type'] == 'audio':
                for fmt in entry['formats']:
                    fmt['vcodec'] = 'none'
                    if fmt.get('ext') == 'mp4':
                        fmt['ext'] = 'm4a'
            entries.append(entry)

        youtube_url = extract_attributes(
            get_element_html_by_id('youtubeInlinePlayer', card) or '').get('data-youtube-url')
        for embed_url in dict.fromkeys(filter(None, [youtube_url, *YoutubeIE._extract_embed_urls(url, card)])):
            entries.append(self.url_result(embed_url, YoutubeIE, url_transparent=True))

        if not entries:
            self.raise_no_formats(
                'This post has no audio or video; use --ignore-no-formats-error '
                'with --write-description and --write-all-thumbnails to save its text and images',
                expected=True, video_id=post_id)
            return {**info, 'formats': []}
        if len(entries) == 1:
            return {**info, **entries[0]}
        return self.playlist_result([
            {**info, **entry, 'id': f'{post_id}-{index}'}
            for index, entry in enumerate(entries, 1)
        ], **info)


class CreatsubChannelIE(InfoExtractor):
    IE_NAME = 'creatsub:channel'
    _VALID_URL = r'https?://(?:www\.)?creatsub\.io/(?P<id>[^/?#:]+)(?::(?P<category>[^/?#]+))?/?(?:[?#]|$)'
    _TESTS = [{
        'url': 'https://creatsub.io/genove-klice',
        'info_dict': {
            'id': 'genove-klice',
            'title': 'Genové klíče',
            'channel': 'Genové klíče',
        },
        'playlist_mincount': 1,
        'expected_warnings': ['Skipping locked post'],
    }, {
        'url': 'https://creatsub.io/genove-klice?categoryid=41',
        'info_dict': {
            'id': 'genove-klice-41',
            'title': 'Genové klíče - audiokniha',
            'channel': 'Genové klíče',
        },
        'playlist_mincount': 1,
        'expected_warnings': ['Skipping locked post'],
    }, {
        'url': 'https://creatsub.io/genove-klice:Audiokniha',
        'only_matching': True,
    }]
    _RETURN_TYPE = 'playlist'
    _PAGE_SIZE = 10

    def _entries(self, channel_id, webpage, category_id):
        seen = set()
        for page in itertools.count():
            if category_id:
                webpage = self._download_json(
                    f'https://creatsub.io/post/category/posts/{category_id}', channel_id,
                    'Downloading category JSON')['html']
            elif page:
                webpage = self._download_json(
                    'https://creatsub.io/load-user-posts', channel_id,
                    f'Downloading page {page + 1}', data=urlencode_postdata({
                        'offset': page * self._PAGE_SIZE,
                        'nick': channel_id,
                    }), headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-Requested-With': 'XMLHttpRequest',
                    })['html']

            new_posts = False
            for card in get_elements_html_by_class('card', webpage):
                post_url = self._search_regex(
                    r'\bdata-url=(["\'])(?P<url>https?://(?:www\.)?creatsub\.io/post/[^"\']+)\1',
                    card, 'post URL', default=None, group='url')
                if not post_url or not CreatsubIE.suitable(post_url):
                    continue
                post_id = CreatsubIE._match_id(post_url)
                if post_id in seen:
                    continue
                seen.add(post_id)
                new_posts = True
                title = clean_html(get_element_by_class('card-title', card))
                if get_element_by_class('bi-lock-fill', card) is not None:
                    self.report_warning(f'Skipping locked post {post_id}: {title}')
                    continue
                yield self.url_result(post_url, CreatsubIE, post_id, title)

            # The category endpoint returns the entire category in one response.
            if category_id or not new_posts:
                return

    def _real_extract(self, url):
        channel_id, category = self._match_valid_url(url).group('id', 'category')
        channel_url = f'https://creatsub.io/{channel_id}'
        webpage = self._download_webpage(channel_url, channel_id)
        categories = {}
        for link in re.findall(r'(?s)<a\b[^>]*>.*?</a>', get_element_by_id('category', webpage) or ''):
            category_id = traverse_obj(parse_qs(urljoin(channel_url, extract_attributes(link).get('href'))), (
                'categoryid', 0, {str}))
            if category_id:
                categories[category_id] = clean_html(get_element_by_class('text-primary', link))

        category_id = traverse_obj(parse_qs(url), ('categoryid', 0))
        if category:
            category = urllib.parse.unquote(category).casefold()
            category_id = next((key for key, name in categories.items() if name and name.casefold() == category), None)
            if not category_id:
                raise ExtractorError(f'Unknown category: {category}', expected=True)
        if category_id and category_id not in categories:
            raise ExtractorError(f'Unknown category ID: {category_id}', expected=True)

        title = self._html_search_meta('profile:username', webpage, default=None) or self._html_search_regex(
            r'(?s)<h1\b[^>]*>\s*<a\b[^>]*>(.*?)</a>', webpage, 'channel title')
        return self.playlist_result(
            self._entries(channel_id, webpage, category_id),
            f'{channel_id}-{category_id}' if category_id else channel_id,
            f'{title} - {categories[category_id]}' if category_id else title,
            channel=title)
