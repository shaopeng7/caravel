"""Contains the logic to create cohesive forms on the explore view"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from collections import OrderedDict
from copy import copy
import math

from flask_babelpkg import lazy_gettext as _
from wtforms import (
    Form, SelectMultipleField, SelectField, TextField, TextAreaField,
    BooleanField, IntegerField, HiddenField, DecimalField)
from wtforms import validators, widgets

from caravel import app

config = app.config

TIMESTAMP_CHOICES = [
    ('smart_date', 'Adaptative formating'),
    ("%m/%d/%Y", '"%m/%d/%Y" | 01/14/2019'),
    ("%Y-%m-%d", '"%Y-%m-%d" | 2019-01-14'),
    ("%Y-%m-%d %H:%M:%S",
     '"%Y-%m-%d %H:%M:%S" | 2019-01-14 01:32:10'),
    ("%H:%M:%S", '"%H:%M:%S" | 01:32:10'),
]


class BetterBooleanField(BooleanField):

    """Fixes the html checkbox to distinguish absent from unchecked

    (which doesn't distinguish False from NULL/missing )
    If value is unchecked, this hidden <input> fills in False value
    """

    def __call__(self, **kwargs):
        html = super(BetterBooleanField, self).__call__(**kwargs)
        html += u'<input type="hidden" name="{}" value="false">'.format(self.name)
        return widgets.HTMLString(html)


class SelectMultipleSortableField(SelectMultipleField):

    """Works along with select2sortable to preserves the sort order"""

    def iter_choices(self):
        d = OrderedDict()
        for value, label in self.choices:
            selected = self.data is not None and self.coerce(value) in self.data
            d[value] = (value, label, selected)
        if self.data:
            for value in self.data:
                if value and value in d:
                    yield d.pop(value)
        while d:
            yield d.popitem(last=False)[1]


class FreeFormSelect(widgets.Select):

    """A WTF widget that allows for free form entry"""

    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        if self.multiple:
            kwargs['multiple'] = True
        html = ['<select %s>' % widgets.html_params(name=field.name, **kwargs)]
        found = False
        for val, label, selected in field.iter_choices():
            html.append(self.render_option(val, label, selected))
            if field.data and val == field.data:
                found = True
        if not found:
            html.insert(1, self.render_option(field.data, field.data, True))
        html.append('</select>')
        return widgets.HTMLString(''.join(html))


class FreeFormSelectField(SelectField):

    """A WTF SelectField that allows for free form input"""

    widget = FreeFormSelect()

    def pre_validate(self, form):
        return


class OmgWtForm(Form):

    """Caravelification of the WTForm Form object"""

    fieldsets = {}
    css_classes = dict()

    def get_field(self, fieldname):
        return getattr(self, fieldname)

    def field_css_classes(self, fieldname):
        if fieldname in self.css_classes:
            return " ".join(self.css_classes[fieldname])
        return ""


class FormFactory(object):

    """Used to create the forms in the explore view dynamically"""

    series_limits = [0, 5, 10, 25, 50, 100, 500]
    fieltype_class = {
        SelectField: 'select2',
        SelectMultipleField: 'select2',
        FreeFormSelectField: 'select2_freeform',
        SelectMultipleSortableField: 'select2Sortable',
    }

    def __init__(self, viz):
        self.viz = viz
        from caravel.viz import viz_types
        viz = self.viz
        datasource = viz.datasource
        if not datasource.metrics_combo:
            raise Exception("Please define at least one metric for your table")
        default_metric = datasource.metrics_combo[0][0]

        gb_cols = datasource.groupby_column_names
        default_groupby = gb_cols[0] if gb_cols else None
        group_by_choices = self.choicify(gb_cols)
        # Pool of all the fields that can be used in Caravel
        field_data = {
            'viz_type': (SelectField, {
                "label": _("Viz"),
                "default": 'table',
                "choices": [(k, v.verbose_name) for k, v in viz_types.items()],
                "description": _("The type of visualization to display")
            }),
            'metrics': (SelectMultipleSortableField, {
                "label": _("Metrics"),
                "choices": datasource.metrics_combo,
                "default": [default_metric],
                "description": _("One or many metrics to display")
            }),
            'metric': (SelectField, {
                "label": _("Metric"),
                "choices": datasource.metrics_combo,
                "default": default_metric,
                "description": _("Choose the metric")
            }),
            'stacked_style': (SelectField, {
                "label": _("Chart Style"),
                "choices": (
                    ('stack', _('stack')),
                    ('stream', _('stream')),
                    ('expand', _('expand')),
                ),
                "default": 'stack',
                "description": ""
            }),
            'linear_color_scheme': (SelectField, {
                "label": _("Color Scheme"),
                "choices": (
                    ('fire', _('fire')),
                    ('blue_white_yellow', _('blue_white_yellow')),
                    ('white_black', _('white_black')),
                    ('black_white', _('black_white')),
                ),
                "default": 'blue_white_yellow',
                "description": ""
            }),
            'normalize_across': (SelectField, {
                "label": _("Normalize Across"),
                "choices": (
                    ('heatmap', _('heatmap')),
                    ('x', _('x')),
                    ('y', _('y')),
                ),
                "default": 'heatmap',
                "description": _(
                    "Color will be rendered based on a ratio "
                    "of the cell against the sum of across this "
                    "criteria")
            }),
            'horizon_color_scale': (SelectField, {
                "label": _("Color Scale"),
                "choices": (
                    ('series', _('series')),
                    ('overall', _('overall')),
                    ('change', _('change')),
                ),
                "default": 'series',
                "description": _("Defines how the color are attributed.")
            }),
            'canvas_image_rendering': (SelectField, {
                "label": _("Rendering"),
                "choices": (
                    ('pixelated', _('pixelated (Sharp)')),
                    ('auto', _('auto (Smooth)')),
                ),
                "default": 'pixelated',
                "description": _(
                    "image-rendering CSS attribute of the canvas object that "
                    "defines how the browser scales up the image")
            }),
            'xscale_interval': (SelectField, {
                "label": _("XScale Interval"),
                "choices": self.choicify(range(1, 50)),
                "default": '1',
                "description": _(
                    "Number of step to take between ticks when "
                    "printing the x scale")
            }),
            'yscale_interval': (SelectField, {
                "label": _("YScale Interval"),
                "choices": self.choicify(range(1, 50)),
                "default": '1',
                "description": _(
                    "Number of step to take between ticks when "
                    "printing the y scale")
            }),
            'bar_stacked': (BetterBooleanField, {
                "label": _("Stacked Bars"),
                "default": False,
                "description": ""
            }),
            'include_series': (BetterBooleanField, {
                "label": _("Include Series"),
                "default": False,
                "description": _("Include series name as an axis")
            }),
            'secondary_metric': (SelectField, {
                "label": _("Color Metric"),
                "choices": datasource.metrics_combo,
                "default": default_metric,
                "description": _("A metric to use for color")
            }),
            'country_fieldtype': (SelectField, {
                "label": _("Country Field Type"),
                "default": 'cca2',
                "choices": (
                    ('name', _('Full name')),
                    ('cioc', _('code International Olympic Committee (cioc)')),
                    ('cca2', _('code ISO 3166-1 alpha-2 (cca2)')),
                    ('cca3', _('code ISO 3166-1 alpha-3 (cca3)')),
                ),
                "description": _(
                    "The country code standard that Caravel should expect "
                    "to find in the [country] column")
            }),
            'groupby': (SelectMultipleSortableField, {
                "label": _("Group by"),
                "choices": self.choicify(datasource.groupby_column_names),
                "description": _("One or many fields to group by")
            }),
            'columns': (SelectMultipleSortableField, {
                "label": _("Columns"),
                "choices": self.choicify(datasource.groupby_column_names),
                "description": _("One or many fields to pivot as columns")
            }),
            'all_columns': (SelectMultipleSortableField, {
                "label": _("Columns"),
                "choices": self.choicify(datasource.column_names),
                "description": _("Columns to display")
            }),
            'all_columns_x': (SelectField, {
                "label": _("X"),
                "choices": self.choicify(datasource.column_names),
                "description": _("Columns to display")
            }),
            'all_columns_y': (SelectField, {
                "label": _("Y"),
                "choices": self.choicify(datasource.column_names),
                "description": _("Columns to display")
            }),
            'druid_time_origin': (FreeFormSelectField, {
                "label": _( "Origin"),
                "choices": (
                    ('', _('default')),
                    ('now', _('now')),
                ),
                "default": '',
                "description": _(
                    "Defines the origin where time buckets start, "
                    "accepts natural dates as in 'now', 'sunday' or '1970-01-01'")
            }),
            'granularity': (FreeFormSelectField, {
                "label": _("Time Granularity"),
                "default": "one day",
                "choices": (
                    ('all', _('all')),
                    ('5 seconds', _('5 seconds')),
                    ('30 seconds', _('30 seconds')),
                    ('1 minute', _('1 minute')),
                    ('5 minutes', _('5 minutes')),
                    ('1 hour', _('1 hour')),
                    ('6 hour', _('6 hour')),
                    ('1 day', _('1 day')),
                    ('7 days', _('7 days')),
                ),
                "description": _(
                    "The time granularity for the visualization. Note that you "
                    "can type and use simple natural language as in '10 seconds', "
                    "'1 day' or '56 weeks'")
            }),
            'domain_granularity': (SelectField, {
                "label": _("Domain"),
                "default": "month",
                "choices": (
                    ('hour', _('hour')),
                    ('day', _('day')),
                    ('week', _('week')),
                    ('month', _('month')),
                    ('year', _('year')),
                ),
                "description": _(
                    "The time unit used for the grouping of blocks")
            }),
            'subdomain_granularity': (SelectField, {
                "label": _("Subdomain"),
                "default": "day",
                "choices": (
                    ('min', _('min')),
                    ('hour', _('hour')),
                    ('day', _('day')),
                    ('week', _('week')),
                    ('month', _('month')),
                ),
                "description": _(
                    "The time unit for each block. Should be a smaller unit than "
                    "domain_granularity. Should be larger or equal to Time Grain")
            }),
            'link_length': (FreeFormSelectField, {
                "label": _("Link Length"),
                "default": "200",
                "choices": self.choicify([
                    '10',
                    '25',
                    '50',
                    '75',
                    '100',
                    '150',
                    '200',
                    '250',
                ]),
                "description": _("Link length in the force layout")
            }),
            'charge': (FreeFormSelectField, {
                "label": _("Charge"),
                "default": "-500",
                "choices": self.choicify([
                    '-50',
                    '-75',
                    '-100',
                    '-150',
                    '-200',
                    '-250',
                    '-500',
                    '-1000',
                    '-2500',
                    '-5000',
                ]),
                "description": _("Charge in the force layout")
            }),
            'granularity_sqla': (SelectField, {
                "label": _("Time Column"),
                "default": datasource.main_dttm_col or datasource.any_dttm_col,
                "choices": self.choicify(datasource.dttm_cols),
                "description": _(
                    "The time column for the visualization. Note that you "
                    "can define arbitrary expression that return a DATETIME "
                    "column in the table editor. Also note that the "
                    "filter bellow is applied against this column or "
                    "expression")
            }),
            'resample_rule': (FreeFormSelectField, {
                "label": _("Resample Rule"),
                "default": '',
                "choices": (
                    ('1T', _('1T')),
                    ('1H', _('1H')),
                    ('1D', _('1D')),
                    ('7D', _('7D')),
                    ('1M', _('1M')),
                    ('1AS', _('1AS')),
                ),
                "description": _("Pandas resample rule")
            }),
            'resample_how': (FreeFormSelectField, {
                "label": _("Resample How"),
                "default": '',
                "choices": (
                     ('', ''),
                     ('mean', _('mean')),
                     ('sum', _('sum')),
                     ('median', _('median')),
                 ),
                "description": _("Pandas resample how")
            }),
            'resample_fillmethod': (FreeFormSelectField, {
                "label": _("Resample Fill Method"),
                "default": '',
                "choices": (
                    ('', ''),
                    ('ffill', _('ffill')),
                    ('bfill', _('bfill')),
                ),
                "description": _("Pandas resample fill method")
            }),
            'since': (FreeFormSelectField, {
                "label": _("Since"),
                "default": "7 days ago",
                "choices": (
                    ('1 hour ago', _('1 hour ago')),
                    ('12 hours ago', _('12 hours ago')),
                    ('1 day ago', _('1 day ago')),
                    ('7 days ago', _('7 days ago')),
                    ('28 days ago', _('28 days ago')),
                    ('90 days ago', _('90 days ago')),
                    ('1 year ago', _('1 year ago')),
                ),
                "description": _(
                    "Timestamp from filter. This supports free form typing and "
                    "natural language as in '1 day ago', '28 days' or '3 years'")
            }),
            'until': (FreeFormSelectField, {
                "label": _("Until"),
                "default": "now",
                "choices": (
                    ('now', _('now')),
                    ('1 day ago', _('1 day ago')),
                    ('7 days ago', _('7 days ago')),
                    ('28 days ago', _('28 days ago')),
                    ('90 days ago', _('90 days ago')),
                    ('1 year ago', _('1 year ago')),
                )
            }),
            'max_bubble_size': (FreeFormSelectField, {
                "label": _("Max Bubble Size"),
                "default": "25",
                "choices": self.choicify([
                    '5',
                    '10',
                    '15',
                    '25',
                    '50',
                    '75',
                    '100',
                ])
            }),
            'whisker_options': (FreeFormSelectField, {
                "label": _("Whisker/outlier options"),
                "default": "Tukey",
                "description": _(
                    "Determines how whiskers and outliers are calculated."),
                "choices": (
                    ('Tukey', _('Tukey')),
                    ('Min/max (no outliers)', _('Min/max (no outliers)')),
                    ('2/98 percentiles', _('2/98 percentiles')),
                    ('9/91 percentiles', _('9/91 percentiles')),
                )
            }),
            'treemap_ratio': (DecimalField, {
                "label": _("Ratio"),
                "default": 0.5 * (1 + math.sqrt(5)),  # d3 default, golden ratio
                "description": _('Target aspect ratio for treemap tiles.'),
            }),
            'number_format': (FreeFormSelectField, {
                "label": _("Number format"),
                "default": '.3s',
                "choices": [
                    ('.3s', '".3s" | 12.3k'),
                    ('.3%', '".3%" | 1234543.210%'),
                    ('.4r', '".4r" | 12350'),
                    ('.3f', '".3f" | 12345.432'),
                    ('+,', '"+," | +12,345.4321'),
                    ('$,.2f', '"$,.2f" | $12,345.43'),
                ],
                "description": _("D3 format syntax for numbers "
                            "https: //github.com/mbostock/\n"
                            "d3/wiki/Formatting")
            }),
            'row_limit': (FreeFormSelectField, {
                "label": _('Row limit'),
                "default": config.get("ROW_LIMIT"),
                "choices": self.choicify(
                    [10, 50, 100, 250, 500, 1000, 5000, 10000, 50000])
            }),
            'limit': (FreeFormSelectField, {
                "label": _('Series limit'),
                "choices": self.choicify(self.series_limits),
                "default": 50,
                "description": _(
                    "Limits the number of time series that get displayed")
            }),
            'rolling_type': (SelectField, {
                "label": _("Rolling"),
                "default": 'None',
                "choices": [(s, s) for s in ['None', 'mean', 'sum', 'std', 'cumsum']],
                "description": _(
                    "Defines a rolling window function to apply, works along "
                    "with the [Periods] text box")
            }),
            'rolling_periods': (IntegerField, {
                "label": _("Periods"),
                "validators": [validators.optional()],
                "description": _(
                    "Defines the size of the rolling window function, "
                    "relative to the time granularity selected")
            }),
            'series': (SelectField, {
                "label": _("Series"),
                "choices": group_by_choices,
                "default": default_groupby,
                "description": _(
                    "Defines the grouping of entities. "
                    "Each serie is shown as a specific color on the chart and "
                    "has a legend toggle")
            }),
            'entity': (SelectField, {
                "label": _("Entity"),
                "choices": group_by_choices,
                "default": default_groupby,
                "description": _("This define the element to be plotted on the chart")
            }),
            'x': (SelectField, {
                "label": _("X Axis"),
                "choices": datasource.metrics_combo,
                "default": default_metric,
                "description": _("Metric assigned to the [X] axis")
            }),
            'y': (SelectField, {
                "label": _("Y Axis"),
                "choices": datasource.metrics_combo,
                "default": default_metric,
                "description": _("Metric assigned to the [Y] axis")
            }),
            'size': (SelectField, {
                "label": _('Bubble Size'),
                "default": default_metric,
                "choices": datasource.metrics_combo
            }),
            'url': (TextField, {
                "label": _("URL"),
                "description": _(
                    "The URL, this field is templated, so you can integrate "
                    "{{ width }} and/or {{ height }} in your URL string."
                ),
                "default": 'https: //www.youtube.com/embed/JkI5rg_VcQ4',
            }),
            'where': (TextField, {
                "label": _("Custom WHERE clause"),
                "default": '',
                "description": _(
                    "The text in this box gets included in your query's WHERE "
                    "clause, as an AND to other criteria. You can include "
                    "complex expression, parenthesis and anything else "
                    "supported by the backend it is directed towards.")
            }),
            'having': (TextField, {
                "label": _("Custom HAVING clause"),
                "default": '',
                "description": _(
                    "The text in this box gets included in your query's HAVING"
                    " clause, as an AND to other criteria. You can include "
                    "complex expression, parenthesis and anything else "
                    "supported by the backend it is directed towards.")
            }),
            'compare_lag': (TextField, {
                "label": _("Comparison Period Lag"),
                "description": _(
                    "Based on granularity, number of time periods to "
                    "compare against")
            }),
            'compare_suffix': (TextField, {
                "label": _("Comparison suffix"),
                "description": _("Suffix to apply after the percentage display")
            }),
            'table_timestamp_format': (FreeFormSelectField, {
                "label": _("Table Timestamp Format"),
                "default": 'smart_date',
                "choices": TIMESTAMP_CHOICES,
                "description": _("Timestamp Format")
            }),
            'series_height': (FreeFormSelectField, {
                "label": _("Series Height"),
                "default": 25,
                "choices": self.choicify([10, 25, 40, 50, 75, 100, 150, 200]),
                "description": _("Pixel height of each series")
            }),
            'x_axis_format': (FreeFormSelectField, {
                "label": _("X axis format"),
                "default": 'smart_date',
                "choices": TIMESTAMP_CHOICES,
                "description": _("D3 format syntax for y axis "
                            "https: //github.com/mbostock/\n"
                            "d3/wiki/Formatting")
            }),
            'y_axis_format': (FreeFormSelectField, {
                "label": _("Y axis format"),
                "default": '.3s',
                "choices": [
                    ('.3s', '".3s" | 12.3k'),
                    ('.3%', '".3%" | 1234543.210%'),
                    ('.4r', '".4r" | 12350'),
                    ('.3f', '".3f" | 12345.432'),
                    ('+,', '"+," | +12,345.4321'),
                    ('$,.2f', '"$,.2f" | $12,345.43'),
                ],
                "description": _("D3 format syntax for y axis "
                            "https: //github.com/mbostock/\n"
                            "d3/wiki/Formatting")
            }),
            'markup_type': (SelectField, {
                "label": _("Markup Type"),
                "choices": (
                    ('markdown', _('markdown')),
                    ('html', _('html'))
                ),
                "default": "markdown",
                "description": _("Pick your favorite markup language")
            }),
            'rotation': (SelectField, {
                "label": _("Rotation"),
                "choices": (
                    ('random', _('random')),
                    ('flat', _('flat')),
                    ('square', _('square')),
                ),
                "default": "random",
                "description": _("Rotation to apply to words in the cloud")
            }),
            'line_interpolation': (SelectField, {
                "label": _("Line Style"),
                "choices": (
                    ('linear', _('linear')),
                    ('basis', _('basis')),
                    ('cardinal', _('cardinal')),
                    ('monotone', _('monotone')),
                    ('step-before', _('step-before')),
                    ('step-after', _('step-after')),
                ),
                "default": 'linear',
                "description": _("Line interpolation as defined by d3.js")
            }),
            'code': (TextAreaField, {
                "label": _("Code"),
                "description": _("Put your code here"),
                "default": ''
            }),
            'pandas_aggfunc': (SelectField, {
                "label": _("Aggregation function"),
                "choices": (
                    ('sum', _('sum')),
                    ('mean', _('mean')),
                    ('min', _('min')),
                    ('max', _('max')),
                    ('median', _('median')),
                    ('stdev', _('stdev')),
                    ('var', _('var')),
                ),
                "default": 'sum',
                "description": _(
                    "Aggregate function to apply when pivoting and "
                    "computing the total rows and columns")
            }),
            'size_from': (TextField, {
                "label": _("Font Size From"),
                "default": "20",
                "description": _("Font size for the smallest value in the list")
            }),
            'size_to': (TextField, {
                "label": _("Font Size To"),
                "default": "150",
                "description": _("Font size for the biggest value in the list")
            }),
            'show_brush': (BetterBooleanField, {
                "label": _("Range Filter"),
                "default": False,
                "description": _(
                    "Whether to display the time range interactive selector")
            }),
            'show_datatable': (BetterBooleanField, {
                "label": _("Data Table"),
                "default": False,
                "description": _("Whether to display the interactive data table")
            }),
            'include_search': (BetterBooleanField, {
                "label": _("Search Box"),
                "default": False,
                "description": _(
                    "Whether to include a client side search box")
            }),
            'show_bubbles': (BetterBooleanField, {
                "label": _("Show Bubbles"),
                "default": False,
                "description": _(
                    "Whether to display bubbles on top of countries")
            }),
            'show_legend': (BetterBooleanField, {
                "label": _("Legend"),
                "default": True,
                "description": _("Whether to display the legend (toggles)")
            }),
            'x_axis_showminmax': (BetterBooleanField, {
                "label": _("X bounds"),
                "default": True,
                "description": _(
                    "Whether to display the min and max values of the X axis")
            }),
            'rich_tooltip': (BetterBooleanField, {
                "label": _("Rich Tooltip"),
                "default": True,
                "description": _(
                    "The rich tooltip shows a list of all series for that"
                    " point in time")
            }),
            'y_axis_zero': (BetterBooleanField, {
                "label": _("Y Axis Zero"),
                "default": False,
                "description": _(
                    "Force the Y axis to start at 0 instead of the minimum "
                    "value")
            }),
            'y_log_scale': (BetterBooleanField, {
                "label": _("Y Log"),
                "default": False,
                "description": _("Use a log scale for the Y axis")
            }),
            'x_log_scale': (BetterBooleanField, {
                "label": _("X Log"),
                "default": False,
                "description": _("Use a log scale for the X axis")
            }),
            'donut': (BetterBooleanField, {
                "label": _("Donut"),
                "default": False,
                "description": _("Do you want a donut or a pie?")
            }),
            'contribution': (BetterBooleanField, {
                "label": _("Contribution"),
                "default": False,
                "description": _("Compute the contribution to the total")
            }),
            'num_period_compare': (IntegerField, {
                "label": _("Period Ratio"),
                "default": None,
                "validators": [validators.optional()],
                "description": _(
                    "[integer] Number of period to compare against, "
                    "this is relative to the granularity selected")
            }),
            'time_compare': (TextField, {
                "label": _("Time Shift"),
                "default": "",
                "description": _(
                    "Overlay a timeseries from a "
                    "relative time period. Expects relative time delta "
                    "in natural language (example:  24 hours, 7 days, "
                    "56 weeks, 365 days")
            }),
            'subheader': (TextField, {
                "label": _("Subheader"),
                "description": _(
                    "Description text that shows up below your Big "
                    "Number")
            }),
        }

        # Override default arguments with form overrides
        for field_name, override_map in viz.form_overrides.items():
            if field_name in field_data:
                field_data[field_name][1].update(override_map)

        self.field_dict = {
            field_name: v[0](**v[1])
            for field_name, v in field_data.items()
        }

    @staticmethod
    def choicify(l):
        return [("{}".format(obj), "{}".format(obj)) for obj in l]

    def get_form(self):
        """Returns a form object based on the viz/datasource/context"""
        viz = self.viz
        field_css_classes = {}
        for name, obj in self.field_dict.items():
            field_css_classes[name] = ['form-control']
            s = self.fieltype_class.get(obj.field_class)
            if s:
                field_css_classes[name] += [s]

        for field in ('show_brush', 'show_legend', 'rich_tooltip'):
            field_css_classes[field] += ['input-sm']

        class QueryForm(OmgWtForm):

            """The dynamic form object used for the explore view"""

            fieldsets = copy(viz.fieldsets)
            css_classes = field_css_classes
            standalone = HiddenField()
            async = HiddenField()
            force = HiddenField()
            extra_filters = HiddenField()
            json = HiddenField()
            slice_id = HiddenField()
            slice_name = HiddenField()
            previous_viz_type = HiddenField(default=viz.viz_type)
            collapsed_fieldsets = HiddenField()
            viz_type = self.field_dict.get('viz_type')

        for field in viz.flat_form_fields():
            setattr(QueryForm, field, self.field_dict[field])

        def add_to_form(attrs):
            for attr in attrs:
                setattr(QueryForm, attr, self.field_dict[attr])

        filter_choices = self.choicify(['in', 'not in'])
        # datasource type specific form elements
        datasource_classname = viz.datasource.__class__.__name__
        time_fields = None
        if datasource_classname == 'SqlaTable':
            QueryForm.fieldsets += ({
                'label': _('SQL'),
                'fields': ['where', 'having'],
                'description': _(
                    "This section exposes ways to include snippets of "
                    "SQL in your query"),
            },)
            add_to_form(('where', 'having'))
            grains = viz.datasource.database.grains()

            if grains:
                time_fields = ('granularity_sqla', 'time_grain_sqla')
                self.field_dict['time_grain_sqla'] = SelectField(
                    _('Time Grain'),
                    choices=self.choicify((grain.name for grain in grains)),
                    default="Time Column",
                    description=_(
                        "The time granularity for the visualization. This "
                        "applies a date transformation to alter "
                        "your time column and defines a new time granularity."
                        "The options here are defined on a per database "
                        "engine basis in the Caravel source code"))
                add_to_form(time_fields)
                field_css_classes['time_grain_sqla'] = ['form-control', 'select2']
                field_css_classes['granularity_sqla'] = ['form-control', 'select2']
            else:
                time_fields = 'granularity_sqla'
                add_to_form((time_fields, ))
        elif datasource_classname == 'DruidDatasource':
            time_fields = ('granularity', 'druid_time_origin')
            add_to_form(('granularity', 'druid_time_origin'))
            field_css_classes['granularity'] = ['form-control', 'select2_freeform']
            field_css_classes['druid_time_origin'] = ['form-control', 'select2_freeform']
            filter_choices = self.choicify(['in', 'not in', 'regex'])
        add_to_form(('since', 'until'))

        filter_cols = viz.datasource.filterable_column_names or ['']
        for i in range(10):
            setattr(QueryForm, 'flt_col_' + str(i), SelectField(
                _('Filter 1'),
                default=filter_cols[0],
                choices=self.choicify(filter_cols)))
            setattr(QueryForm, 'flt_op_' + str(i), SelectField(
                _('Filter 1'),
                default='in',
                choices=filter_choices))
            setattr(
                QueryForm, 'flt_eq_' + str(i),
                TextField(_("Super"), default=''))

        if time_fields:
            QueryForm.fieldsets = ({
                'label': _('Time'),
                'fields': (
                    time_fields,
                    ('since', 'until'),
                ),
                'description': _("Time related form attributes"),
            },) + tuple(QueryForm.fieldsets)
        return QueryForm
