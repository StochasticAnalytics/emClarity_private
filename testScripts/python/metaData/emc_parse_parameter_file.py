import ast
import os
from emc_type_traits import EmcTypeTraits

class EmcParameterFile:
    def __init__(self, parameter_file_path):
        self.parameter_file_path = parameter_file_path
        self.type_checker = EmcTypeTraits()
        self.string_keys = {
            'subtomometa', 'ali_mtype', 'cls_mtype', 'raw_mtype', 'fsc_mtype',
            'pca_distmeasure', 'kms_mtype', 'flgprecision', 'tmp_xcfscale',
            'fastscratchdisk', 'tmp_erasemasktype', 'startingdirection', 'peak_mtype', 'symmetry',
            'gmm_covariance_type', 'distance_metric'
        }
        self.emc_params = self._parse_parameter_file()

    def _parse_parameter_file(self):
        emc_params = {}
        try:
            with open(self.parameter_file_path, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"Error: Parameter file not found at {self.parameter_file_path}")
            return None

        raw_lines = []
        for line_content in lines:
            cleaned_line = line_content.split('%', 1)[0].strip()
            if cleaned_line:
                raw_lines.append(cleaned_line)

        last_parsed_parameter = 'none'
        for line_content in raw_lines:
            parts = line_content.split('=', 1)
            if len(parts) == 2:
                name = parts[0].strip()
                value_str = parts[1].strip()
                if not name:
                    print(f"Warning: Empty parameter name in line: '{line_content}'")
                    continue
                if name.lower() in self.string_keys:
                    emc_params[name] = value_str
                else:
                    try:
                        emc_params[name] = ast.literal_eval(value_str)
                    except (ValueError, SyntaxError):
                        print(f"Warning: Could not parse value for '{name}' ('{value_str}') as a standard Python literal. Storing as string.")
                        emc_params[name] = value_str
                last_parsed_parameter = name
            else:
                print(f"Last successfully parsed parameter: {last_parsed_parameter}")
                print(f"Error: Could not split Name=Value pair for line: '{line_content}'")

        # --- Assertions, Defaults, and Derived Parameters ---
        # fastScratchDisk
        if 'fastScratchDisk' in emc_params:
            if str(emc_params['fastScratchDisk']).lower() == 'ram':
                emc_cache_mem_str = os.getenv('EMC_CACHE_MEM')
                if not emc_cache_mem_str:
                    print('Did not find environment variable EMC_CACHE_MEM. Skipping RAM disk for fastScratchDisk.')
                    emc_params['fastScratchDisk'] = ''
                else:
                    try:
                        emc_cache_mem_val = float(emc_cache_mem_str)
                        if emc_cache_mem_val < 32:
                            print(f'EMC_CACHE_MEM ({emc_cache_mem_val}GB) is less than 32GB. Not using RAM disk.')
                            emc_params['fastScratchDisk'] = ''
                        else:
                            mcr_cache_root = os.getenv('MCR_CACHE_ROOT')
                            if mcr_cache_root:
                                emc_params['fastScratchDisk'] = mcr_cache_root
                            else:
                                print('MCR_CACHE_ROOT environment variable not set. Cannot use RAM disk.')
                                emc_params['fastScratchDisk'] = ''
                    except ValueError:
                        print(f"Warning: Could not convert EMC_CACHE_MEM ('{emc_cache_mem_str}') to float.")
                        emc_params['fastScratchDisk'] = ''
        else:
            emc_params['fastScratchDisk'] = ''

        # nGPUs
        if 'nGPUs' in emc_params:
            self.type_checker.assert_numeric(emc_params['nGPUs'], 1, [1, 1000], param_name='nGPUs')
        else:
            raise ValueError('nGPUs is a required parameter')

        # nCpuCores
        if 'nCpuCores' in emc_params:
            self.type_checker.assert_numeric(emc_params['nCpuCores'], 1, [1, 1000], param_name='nCpuCores')
        else:
            raise ValueError('nCpuCores is a required parameter')

        # symmetry
        symmetry_has_been_checked = False
        if 'symmetry' not in emc_params:
            raise ValueError('You must now specify a symmetry=X parameter, where symmetry E (C1,C2..CX,O,I)')
        # TODO: Add asserts on allowed values for symmetry parameter using type_checker.assert_string_value
        symmetry_has_been_checked = True

        # PIXEL_SIZE
        if 'PIXEL_SIZE' in emc_params:
            self.type_checker.assert_numeric(emc_params['PIXEL_SIZE'], 1, [0, 100e-10], param_name='PIXEL_SIZE')
            emc_params['pixel_size_si'] = emc_params['PIXEL_SIZE']
            emc_params['pixel_size_angstroms'] = emc_params['PIXEL_SIZE'] * 10**10
        else:
            raise ValueError('PIXEL_SIZE is a required parameter')

        # Cs
        if 'Cs' in emc_params:
            self.type_checker.assert_numeric(emc_params['Cs'], 1, [0, 10e-3], param_name='Cs')
        else:
            raise ValueError('Cs is a required parameter')

        # VOLTAGE
        if 'VOLTAGE' in emc_params:
            self.type_checker.assert_numeric(emc_params['VOLTAGE'], 1, [20e3, 1000e3], param_name='VOLTAGE')
        else:
            raise ValueError('VOLTAGE is a required parameter')

        # AMPCONT
        if 'AMPCONT' in emc_params:
            self.type_checker.assert_numeric(emc_params['AMPCONT'], 1, [0.0, 1.0], param_name='AMPCONT')
            if emc_params.get('Cs') == 0:
                emc_params['Cs'] = 1e-10
        else:
            raise ValueError('AMPCONT is a required parameter')

        # --- Optional Parameters & Defaults (examples) ---
        if 'nPeaks' in emc_params:
            self.type_checker.assert_numeric(emc_params['nPeaks'], 1, param_name='nPeaks')
        else:
            emc_params['nPeaks'] = 1

        if 'CUTPADDING' in emc_params:
            self.type_checker.assert_numeric(emc_params['CUTPADDING'], 1, param_name='CUTPADDING')
        else:
            emc_params['CUTPADDING'] = 20
    
        # Deprecated substitutions examples
        emc_params = self.type_checker.assert_deprecated_substitution(emc_params, 'ccc_cutoff', 'flgCCCcutoff')
        if 'flgCCCcutoff' in emc_params:
            self.type_checker.assert_numeric(emc_params['flgCCCcutoff'], 1, param_name='flgCCCcutoff')
        else:
            emc_params['flgCCCcutoff'] = 0.0

        emc_params = self.type_checker.assert_deprecated_substitution(emc_params, 'projectVolumes', 'flgProjectVolumes')
        if 'flgProjectVolumes' in emc_params:
            self.type_checker.assert_boolean(emc_params['flgProjectVolumes'], param_name='flgProjectVolumes')
        else:
            emc_params['flgProjectVolumes'] = False

        emc_params = self.type_checker.assert_deprecated_substitution(emc_params, 'limit_to_one_core', 'flgLimitToOneProcess')
        if 'flgLimitToOneProcess' in emc_params:
            self.type_checker.assert_boolean(emc_params['flgLimitToOneProcess'], param_name='flgLimitToOneProcess')
        else:
            emc_params['flgLimitToOneProcess'] = False

        if emc_params.get('flgLimitToOneProcess') == True:
            emc_params['nCpuCores'] = 1

        if 'force_no_symmetry' in emc_params:
            self.type_checker.assert_boolean(emc_params['force_no_symmetry'], param_name='force_no_symmetry')
            if not symmetry_has_been_checked:
                 raise RuntimeError('force_no_symmetry must be after symmetry check')
            if emc_params['force_no_symmetry']:
                emc_params['symmetry'] = 'C1'
        else:
            emc_params['force_no_symmetry'] = True
            if emc_params['force_no_symmetry'] and symmetry_has_been_checked:
                 emc_params['symmetry'] = 'C1'

        print("Info: Parameter parsing complete. Note that many assertions, defaults, and derived parameter calculations from the original MATLAB script may be simplified or pending full implementation in this Python version.")
        return emc_params

    def get(self, key, default=None):
        return self.emc_params.get(key, default)

    def as_dict(self):
        return dict(self.emc_params)

if __name__ == '__main__':
    param_file = "param0.m"
    if not os.path.exists(param_file) and not os.path.exists("../../../docs/exampleParametersAndRunScript/param0.m"):
        print(f"Test file '{param_file}' not found. Creating a dummy one for demonstration.")
        with open(param_file, "w") as f:
            f.write("subTomoMeta=emClarity_tutorial % project name\n")
            f.write("fastScratchDisk=/scratch/user\n")
            f.write("nGPUs=2\n")
            f.write("nCpuCores=12\n")
            f.write("PIXEL_SIZE=2.0e-10\n")
            f.write("Cs=2.7e-3\n")
            f.write("VOLTAGE=300e3\n")
            f.write("AMPCONT=0.07\n")
            f.write("symmetry=C1\n")
            f.write("particleRadius=[100,100,100]\n")
            f.write("someBooleanFlag=True\n")
            f.write("anotherBoolean=0\n")
            f.write("limit_to_one_core=false\n") 
            f.write("force_no_symmetry=false\n")
    elif not os.path.exists(param_file) and os.path.exists("../../../docs/exampleParametersAndRunScript/param0.m"):
        param_file = "../../../docs/exampleParametersAndRunScript/param0.m"


    print(f"Parsing '{param_file}'...")
    emc_file = EmcParameterFile(param_file)
    parameters = emc_file.as_dict()

    if parameters:
        print("\n--- Parsed Parameters ---")
        for key, value in parameters.items():
            print(f"{key}: {value} (type: {type(value).__name__})")
        print("--- End of Parameters ---")
