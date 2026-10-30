import unittest
from pathlib import Path

from src.setup_project import prepare
from test_data_pipeline import order,temporary_directory,write_source


class SetupTests(unittest.TestCase):
    def test_different_existing_raw_input_is_preserved(self):
        with temporary_directory() as temp:
            root=Path(temp)
            source=root/'supplied.csv'
            write_source(source,[order()])
            target=root/'checkout/data/raw/orders_sample.csv'
            target.parent.mkdir(parents=True)
            target.write_text('existing original input',encoding='utf-8')
            before=target.read_bytes()
            with self.assertRaisesRegex(ValueError,'different raw dataset'):
                prepare(source,root/'checkout')
            self.assertEqual(target.read_bytes(),before)

    def test_malformed_source_does_not_create_outputs(self):
        with temporary_directory() as temp:
            root=Path(temp)
            source=root/'supplied.csv'
            source.write_text('not,the,schema\n1,2,3\n',encoding='utf-8')
            with self.assertRaises(ValueError):
                prepare(source,root/'checkout')
            self.assertFalse((root/'checkout').exists())


if __name__=='__main__':
    unittest.main()
