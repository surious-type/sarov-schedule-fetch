import unittest

from fetch_schedule import extract_course_pdf_links


class ParserTests(unittest.TestCase):
    def test_uses_newest_semester_and_only_second_course(self):
        html = """
        <html><body>
          <h4>Осенний семестр 2025\2026 учебного года</h4>
          <p>2 курс</p>
          <a href="/sites/default/files/2025-09/2_course_01_old.pdf">Неделя 1</a>

          <h4>Осенний семестр 2026/2027 учебного года</h4>
          <p>1 курс</p>
          <a href="/sites/default/files/2026-09/1_course_01.pdf">Неделя 1</a>

          <p><strong>2 курс</strong></p>
          <a href="/sites/default/files/2026-09/2_course_01.pdf">Неделя 1 (1 - 5 сентября)</a>
          <a href="/sites/default/files/2026-09/2_course_02.pdf">Неделя 2 (7 - 12 сентября)</a>

          <p>Аспирантура</p>
          <a href="/sites/default/files/2026-09/postgrad.pdf">Неделя 1</a>
        </body></html>
        """

        semester, links = extract_course_pdf_links(html, course=2)

        self.assertEqual(semester, "Осенний семестр 2026/2027 учебного года")
        self.assertEqual([x["week_number"] for x in links], [1, 2])
        self.assertEqual(
            [x["source_url"] for x in links],
            [
                "https://sarov.msu.ru/sites/default/files/2026-09/2_course_01.pdf",
                "https://sarov.msu.ru/sites/default/files/2026-09/2_course_02.pdf",
            ],
        )

    def test_ignores_external_and_non_pdf_links(self):
        html = """
        <h4>Весенний семестр 2027/2028 учебного года</h4>
        <p>2 курс</p>
        <a href="https://example.com/file.pdf">Неделя 1</a>
        <a href="/sites/default/files/2027-02/readme.txt">Неделя 2</a>
        <a href="/sites/default/files/2027-02/2_course_03.pdf?download=1">Неделя 3</a>
        <p>3 курс</p>
        """

        semester, links = extract_course_pdf_links(html, course=2)

        self.assertEqual(semester, "Весенний семестр 2027/2028 учебного года")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["week_number"], 3)
        self.assertEqual(
            links[0]["source_url"],
            "https://sarov.msu.ru/sites/default/files/2027-02/2_course_03.pdf",
        )

    def test_fails_when_course_block_missing(self):
        html = """
        <h4>Осенний семестр 2026/2027 учебного года</h4>
        <p>1 курс</p>
        <a href="/sites/default/files/2026-09/1_course_01.pdf">Неделя 1</a>
        """

        with self.assertRaisesRegex(RuntimeError, "2 курс"):
            extract_course_pdf_links(html, course=2)


if __name__ == "__main__":
    unittest.main()
