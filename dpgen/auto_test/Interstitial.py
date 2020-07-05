import glob
import json
import os
import re

from monty.serialization import loadfn, dumpfn
from pymatgen.analysis.defects.generators import InterstitialGenerator
from pymatgen.core.structure import Structure

from dpgen.auto_test.Property import Property
from dpgen.auto_test.refine import make_refine
from dpgen.auto_test.reproduce import make_repro
from dpgen.auto_test.reproduce import post_repro


class Interstitial(Property):
    def __init__(self,
                 parameter):
        parameter['reproduce'] = parameter.get('reproduce', False)
        self.reprod = parameter['reproduce']
        if not self.reprod:
            if not ('init_from_suffix' in parameter and 'output_suffix' in parameter):
                default_supercell = [1, 1, 1]
                parameter['supercell'] = parameter.get('supercell', default_supercell)
                self.supercell = parameter['supercell']
                self.insert_ele = parameter['insert_ele']
            parameter['cal_type'] = parameter.get('cal_type', 'relaxation')
            self.cal_type = parameter['cal_type']
            default_cal_setting = {"relax_pos": True,
                                   "relax_shape": True,
                                   "relax_vol": True}
            if 'cal_setting' not in parameter:
                parameter['cal_setting'] = default_cal_setting
            else:
                if "relax_pos" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_pos'] = default_cal_setting['relax_pos']
                if "relax_shape" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_shape'] = default_cal_setting['relax_shape']
                if "relax_vol" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_vol'] = default_cal_setting['relax_vol']
            self.cal_setting = parameter['cal_setting']
        else:
            parameter['cal_type'] = 'static'
            self.cal_type = parameter['cal_type']
            default_cal_setting = {"relax_pos": False,
                                   "relax_shape": False,
                                   "relax_vol": False}
            if 'cal_setting' not in parameter:
                parameter['cal_setting'] = default_cal_setting
            else:
                if "relax_pos" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_pos'] = default_cal_setting['relax_pos']
                if "relax_shape" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_shape'] = default_cal_setting['relax_shape']
                if "relax_vol" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_vol'] = default_cal_setting['relax_vol']
            self.cal_setting = parameter['cal_setting']
            parameter['init_from_suffix'] = parameter.get('init_from_suffix', '00')
            self.init_from_suffix = parameter['init_from_suffix']
        self.parameter = parameter

    def make_confs(self,
                   path_to_work,
                   path_to_equi,
                   refine=False):
        path_to_work = os.path.abspath(path_to_work)
        path_to_equi = os.path.abspath(path_to_equi)

        if 'start_confs_path' in self.parameter and os.path.exists(self.parameter['start_confs_path']):
            init_path_list = glob.glob(os.path.join(self.parameter['start_confs_path'], '*'))
            struct_init_name_list = []
            for ii in init_path_list:
                struct_init_name_list.append(ii.split('/')[-1])
            struct_output_name = path_to_work.split('/')[-2]
            assert struct_output_name in struct_init_name_list
            path_to_equi = os.path.abspath(os.path.join(self.parameter['start_confs_path'],
                                                        struct_output_name, 'relaxation', 'relax_task'))

        task_list = []
        cwd = os.getcwd()

        if self.reprod:
            print('interstitial reproduce starts')
            if 'init_data_path' not in self.parameter:
                raise RuntimeError("please provide the initial data path to reproduce")
            init_data_path = os.path.abspath(self.parameter['init_data_path'])
            task_list = make_repro(init_data_path, self.init_from_suffix,
                                   path_to_work, self.parameter.get('last_frame', False))
            os.chdir(cwd)

        else:
            if refine:
                print('interstitial refine starts')
                task_list = make_refine(self.parameter['init_from_suffix'],
                                        self.parameter['output_suffix'],
                                        path_to_work)

                init_from_path = re.sub(self.parameter['output_suffix'][::-1],
                                        self.parameter['init_from_suffix'][::-1],
                                        path_to_work[::-1], count=1)[::-1]
                task_list_basename = list(map(os.path.basename, task_list))

                os.chdir(path_to_work)
                if os.path.isfile('element.out'):
                    os.remove('element.out')
                if os.path.islink('element.out'):
                    os.remove('element.out')
                os.symlink(os.path.relpath(os.path.join(init_from_path, 'element.out')), 'element.out')
                os.chdir(cwd)

                for ii in task_list_basename:
                    init_from_task = os.path.join(init_from_path, ii)
                    output_task = os.path.join(path_to_work, ii)
                    os.chdir(output_task)
                    if os.path.isfile('supercell.json'):
                        os.remove('supercell.json')
                    if os.path.islink('supercell.json'):
                        os.remove('supercell.json')
                    os.symlink(os.path.relpath(os.path.join(init_from_task, 'supercell.json')), 'supercell.json')
                os.chdir(cwd)

            else:
                equi_contcar = os.path.join(path_to_equi, 'CONTCAR')
                if not os.path.exists(equi_contcar):
                    raise RuntimeError("please do relaxation first")

                ss = Structure.from_file(equi_contcar)
                # gen defects
                dss = []
                insert_element_task = os.path.join(path_to_work, 'element.out')
                if os.path.isfile(insert_element_task):
                    os.remove(insert_element_task)

                for ii in self.insert_ele:
                    vds = InterstitialGenerator(ss, ii)
                    for jj in vds:
                        temp = jj.generate_defect_structure(self.supercell)
                        smallest_distance = list(set(temp.distance_matrix.ravel()))[1]
                        if 'conf_filters' in self.parameter and 'min_dist' in self.parameter['conf_filters']:
                            min_dist = self.parameter['conf_filters']['min_dist']
                            if smallest_distance >= min_dist:
                                dss.append(temp)
                                with open(insert_element_task, 'a+') as fout:
                                    print(ii, file=fout)
                        else:
                            dss.append(temp)
                            with open(insert_element_task, 'a+') as fout:
                                print(ii, file=fout)
                #            dss.append(jj.generate_defect_structure(self.supercell))

                print('gen interstitial with supercell ' + str(self.supercell) + ' with element ' + str(self.insert_ele))
                os.chdir(path_to_work)
                if os.path.isfile('POSCAR'):
                    os.remove('POSCAR')
                if os.path.islink('POSCAR'):
                    os.remove('POSCAR')
                os.symlink(os.path.relpath(equi_contcar), 'POSCAR')
                #           task_poscar = os.path.join(output, 'POSCAR')

                for ii in range(len(dss)):
                    output_task = os.path.join(path_to_work, 'task.%06d' % ii)
                    os.makedirs(output_task, exist_ok=True)
                    os.chdir(output_task)
                    for jj in ['INCAR', 'POTCAR', 'POSCAR', 'conf.lmp', 'in.lammps']:
                        if os.path.exists(jj):
                            os.remove(jj)
                    task_list.append(output_task)
                    dss[ii].to('POSCAR', 'POSCAR')
                    # np.savetxt('supercell.out', self.supercell, fmt='%d')
                    dumpfn(self.supercell, 'supercell.json')
                os.chdir(cwd)

        return task_list

    def post_process(self, task_list):
        pass

    def task_type(self):
        return self.parameter['type']

    def task_param(self):
        return self.parameter

    def _compute_lower(self,
                       output_file,
                       all_tasks,
                       all_res):
        output_file = os.path.abspath(output_file)
        res_data = {}
        ptr_data = os.path.dirname(output_file) + '\n'

        if not self.reprod:
            with open(os.path.join(os.path.dirname(output_file), 'element.out'), 'r') as fin:
                fc = fin.read().split('\n')
            ptr_data += "Insert_ele-Struct: Inter_E(eV)  E(eV) equi_E(eV)\n"
            idid = -1
            for ii in all_tasks:
                idid += 1
                structure_dir = os.path.basename(ii)
                task_result = loadfn(all_res[idid])
                natoms = task_result['atom_numbs'][0]
                equi_path = os.path.abspath(os.path.join(os.path.dirname(output_file), '../relaxation/relax_task'))
                equi_result = loadfn(os.path.join(equi_path, 'result.json'))
                equi_epa = equi_result['energies'][-1] / equi_result['atom_numbs'][0]
                evac = task_result['energies'][-1] - equi_epa * natoms

                supercell_index = loadfn(os.path.join(ii, 'supercell.json'))
                # insert_ele = loadfn(os.path.join(ii, 'task.json'))['insert_ele'][0]
                insert_ele = fc[idid]
                ptr_data += "%s: %7.3f  %7.3f %7.3f \n" % (
                    insert_ele + '-' + str(supercell_index) + '-' + structure_dir, evac,
                    task_result['energies'][-1], equi_epa * natoms)
                res_data[insert_ele + '-' + str(supercell_index) + '-' + structure_dir] = [evac,
                                                                                           task_result['energies'][-1],
                                                                                           equi_epa * natoms]

        else:
            if 'init_data_path' not in self.parameter:
                raise RuntimeError("please provide the initial data path to reproduce")
            init_data_path = os.path.abspath(self.parameter['init_data_path'])
            res_data, ptr_data = post_repro(init_data_path, self.parameter['init_from_suffix'],
                                            all_tasks, ptr_data, self.parameter.get('last_frame', False))

        with open(output_file, 'w') as fp:
            json.dump(res_data, fp, indent=4)

        return res_data, ptr_data
