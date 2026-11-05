from power_desk_elt.ingest.sources.entsoe_eic import IssuingOffice

# the table's layout on the EIC page (2026-11-05): link and icon cells, zero-width spaces, a header spanning cells
PUBLISHED_TABLE = """
<table id="lio-list"><thead><tr><th>LIO Code</th><th>Name</th><th>Country</th><th>Website</th><th>EIC site</th>
<th>Email</th><th colspan="2">Operates in</th></tr></thead><tbody>
<tr id="12"><td>12</td><td>Swissgrid</td><td>CH</td>
<td>&#8203; <a href="https://www.swissgrid.ch/"><i class="ee-icon-globe"></i></a></td><td>&#8203;</td>
<td><a href="mailto:eic.io@swissgrid.ch">&#8203;<i class="ee-icon-envelope"></i></a></td>
<td>&#8203; <i class="ee-icon-elec"></i> <span class="small-80">(except X codes)</span></td>
<td><i class="ee-icon-gas"></i> &#8203;</td><td></td></tr></tbody></table>
"""


def test_issuing_offices_are_the_table_cells_by_header_as_published():
    assert IssuingOffice.parse(PUBLISHED_TABLE) == [
        {
            "LIO Code": "12",
            "Name": "Swissgrid",
            "Country": "CH",
            "Website": "https://www.swissgrid.ch/",
            "EIC site": None,
            "Email": "mailto:eic.io@swissgrid.ch",
            "Operates in": "ee-icon-elec (except X codes) ee-icon-gas",
        }
    ]
