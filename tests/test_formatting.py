from pixiv_gallery.formatting import build_text
from pixiv_gallery.models import Illustration

def test_build_text_includes_metadata_and_link():
    text = build_text([Illustration(id=7,title='Sunset',user_name='A',tags=['sunset'])])
    assert 'Sunset' in text and 'https://www.pixiv.net/artworks/7' in text

def test_build_text_can_hide_metadata():
    assert build_text([Illustration(id=7)], include_metadata=False) == '为你找到 1 张 Pixiv 插画。'
