from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Get an item from a dictionary by key.
    Usage: {{ mydict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter(name='sdg_title')
def sdg_title(sdg_number):
    """
    Convert SDG number to its full title.
    Usage: {{ sdg_number|sdg_title }}
    """
    sdg_titles = {
        '1': '1. No Poverty',
        '2': '2. Zero Hunger',
        '3': '3. Good Health and Well-being',
        '4': '4. Quality Education',
        '5': '5. Gender Equality',
        '6': '6. Clean Water and Sanitation',
        '7': '7. Affordable and Clean Energy',
        '8': '8. Decent Work and Economic Growth',
        '9': '9. Industry, Innovation and Infrastructure',
        '10': '10. Reduced Inequalities',
        '11': '11. Sustainable Cities and Communities',
        '12': '12. Responsible Consumption and Production',
        '13': '13. Climate Action',
        '14': '14. Life Below Water',
        '15': '15. Life on Land',
        '16': '16. Peace, Justice and Strong Institutions',
        '17': '17. Partnerships for the Goals'
    }
    return sdg_titles.get(str(sdg_number), sdg_number)
