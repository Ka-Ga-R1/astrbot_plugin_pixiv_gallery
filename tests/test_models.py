from pixiv_gallery.models import Illustration

def test_illustration_flags_follow_pixiv_x_restrict():
    assert Illustration(id=1, x_restrict=0).is_r18 is False
    assert Illustration(id=2, x_restrict=1).is_r18 is True
    assert Illustration(id=3, x_restrict=2).is_r18g is True
