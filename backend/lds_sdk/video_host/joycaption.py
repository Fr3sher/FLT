"""Named joycaption operations shared with the host; no module handle escapes."""

def availability(*args, **kwargs):
    from app.services.joycaption import availability
    return availability(*args, **kwargs)


def caption_images_joycaption(*args, **kwargs):
    from app.services.joycaption import caption_images_joycaption
    return caption_images_joycaption(*args, **kwargs)



__all__ = ['availability', 'caption_images_joycaption']
