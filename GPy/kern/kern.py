# Copyright (c) 2012, GPy authors (see AUTHORS.txt).
# Licensed under the BSD 3-clause license (see LICENSE.txt)


import numpy as np
from ..core.parameterised import parameterised
from functools import partial
from kernpart import kernpart


class kern(parameterised):
    def __init__(self,D,parts=[], input_slices=None):
        """
        This kernel does 'compound' structures.

        The compund structure enables many features of GPy, including
         - Hierarchical models
         - Correleated output models
         - multi-view learning

        Hadamard product and outer-product kernels will require a new class.
        This feature is currently WONTFIX. for small number sof inputs, you can use the sympy kernel for this.

        :param D: The dimensioality of the kernel's input space
        :type D: int
        :param parts: the 'parts' (PD functions) of the kernel
        :type parts: list of kernpart objects
        :param input_slices: the slices on the inputs which apply to each kernel
        :type input_slices: list of slice objects, or list of bools

        """
        self.parts = parts
        self.Nparts = len(parts)
        self.Nparam = sum([p.Nparam for p in self.parts])

        self.D = D

        #deal with input_slices
        if input_slices is None:
            self.input_slices = [slice(None) for p in self.parts]
        else:
            assert len(input_slices)==len(self.parts)
            self.input_slices = [sl if type(sl) is slice else slice(None) for sl in input_slices]

        for p in self.parts:
            assert isinstance(p,kernpart), "bad kernel part"


        self.compute_param_slices()

        parameterised.__init__(self)

    def compute_param_slices(self):
        """create a set of slices that can index the parameters of each part"""
        self.param_slices = []
        count = 0
        for p in self.parts:
            self.param_slices.append(slice(count,count+p.Nparam))
            count += p.Nparam

    def _process_slices(self,slices1=None,slices2=None):
        """
        Format the slices so that they can easily be used.
        Both slices can be any of three things:
         - If None, the new points covary through every kernel part (default)
         - If a list of slices, the i^th slice specifies which data are affected by the i^th kernel part
         - If a list of booleans, specifying which kernel parts are active

        if the second arg is False, return only slices1

        returns actual lists of slice objects
        """
        if slices1 is None:
            slices1 = [slice(None)]*self.Nparts
        elif all([type(s_i) is bool for s_i in slices1]):
            slices1 = [slice(None) if s_i else slice(0) for s_i in slices1]
        else:
            assert all([type(s_i) is slice for s_i in slices1]), "invalid slice objects"
        if slices2 is None:
            slices2 = [slice(None)]*self.Nparts
        elif slices2 is False:
            return slices1
        elif all([type(s_i) is bool for s_i in slices2]):
            slices2 = [slice(None) if s_i else slice(0) for s_i in slices2]
        else:
            assert all([type(s_i) is slice for s_i in slices2]), "invalid slice objects"
        return slices1, slices2

    def __add__(self,other):
        assert self.D == other.D
        newkern =  kern(self.D,self.parts+other.parts, self.input_slices + other.input_slices)
        #transfer constraints:
        newkern.constrained_positive_indices = np.hstack((self.constrained_positive_indices, self.Nparam + other.constrained_positive_indices))
        newkern.constrained_negative_indices = np.hstack((self.constrained_negative_indices, self.Nparam + other.constrained_negative_indices))
        newkern.constrained_bounded_indices = self.constrained_bounded_indices + [self.Nparam + x for x in other.constrained_bounded_indices]
        newkern.constrained_bounded_lowers = self.constrained_bounded_lowers + other.constrained_bounded_lowers
        newkern.constrained_bounded_uppers = self.constrained_bounded_uppers + other.constrained_bounded_uppers
        newkern.constrained_fixed_indices = self.constrained_fixed_indices + [self.Nparam + x for x in other.constrained_fixed_indices]
        newkern.constrained_fixed_values = self.constrained_fixed_values + other.constrained_fixed_values
        newkern.tied_indices = self.tied_indices + [self.Nparam + x for x in other.tied_indices]
        return newkern
    def add(self,other):
        """
        Add another kernel to this one. Both kernels are defined on the same _space_
        :param other: the other kernel to be added
        :type other: GPy.kern
        """
        return self + other

    def add_orthogonal(self,other):
        """
        Add another kernel to this one. Both kernels are defined on separate spaces
        :param other: the other kernel to be added
        :type other: GPy.kern
        """
        #deal with input slices
        D = self.D + other.D
        self_input_slices = [slice(*sl.indices(self.D)) for sl in self.input_slices]
        other_input_indices = [sl.indices(other.D) for sl in other.input_slices]
        other_input_slices = [slice(i[0]+self.D,i[1]+self.D,i[2]) for i in other_input_indices]

        newkern = kern(D, self.parts + other.parts, self_input_slices + other_input_slices)

        #transfer constraints:
        newkern.constrained_positive_indices = np.hstack((self.constrained_positive_indices, self.Nparam + other.constrained_positive_indices))
        newkern.constrained_negative_indices = np.hstack((self.constrained_negative_indices, self.Nparam + other.constrained_negative_indices))
        newkern.constrained_bounded_indices = self.constrained_bounded_indices + [self.Nparam + x for x in other.constrained_bounded_indices]
        newkern.constrained_bounded_lowers = self.constrained_bounded_lowers + other.constrained_bounded_lowers
        newkern.constrained_bounded_uppers = self.constrained_bounded_uppers + other.constrained_bounded_uppers
        newkern.constrained_fixed_indices = self.constrained_fixed_indices + [self.Nparam + x for x in other.constrained_fixed_indices]
        newkern.constrained_fixed_values = self.constrained_fixed_values + other.constrained_fixed_values
        newkern.tied_indices = self.tied_indices + [self.Nparam + x for x in other.tied_indices]
        return newkern

    def get_param(self):
        return np.hstack([p.get_param() for p in self.parts])

    def set_param(self,x):
        [p.set_param(x[s]) for p, s in zip(self.parts, self.param_slices)]

    def get_param_names(self):
        return sum([[k.name+'_'+str(i)+'_'+n for n in k.get_param_names()] for i,k in enumerate(self.parts)],[])

    def K(self,X,X2=None,slices1=None,slices2=None):
        assert X.shape[1]==self.D
        slices1, slices2 = self._process_slices(slices1,slices2)
        if X2 is None:
            X2 = X
        target = np.zeros((X.shape[0],X2.shape[0]))
        [p.K(X[s1,i_s],X2[s2,i_s],target=target[s1,s2]) for p,i_s,s1,s2 in zip(self.parts,self.input_slices,slices1,slices2)]
        return target

    def dK_dtheta(self,partial,X,X2=None,slices1=None,slices2=None):
        """
        :param partial: An array of partial derivaties, dL_dK
        :type partial: Np.ndarray (N x M)
        :param X: Observed data inputs
        :type X: np.ndarray (N x D)
        :param X2: Observed dara inputs (optional, defaults to X)
        :type X2: np.ndarray (M x D)
        :param slices1: a slice object for each kernel part, describing which data are affected by each kernel part
        :type slices1: list of slice objects, or list of booleans
        :param slices2: slices for X2
        """
        assert X.shape[1]==self.D
        slices1, slices2 = self._process_slices(slices1,slices2)
        if X2 is None:
            X2 = X
        target = np.zeros(self.Nparam)
        [p.dK_dtheta(partial[s1,s2],X[s1,i_s],X2[s2,i_s],target[ps]) for p,i_s,ps,s1,s2 in zip(self.parts, self.input_slices, self.param_slices, slices1, slices2)]
        return target

    def dK_dX(self,partial,X,X2=None,slices1=None,slices2=None):
        if X2 is None:
            X2 = X
        slices1, slices2 = self._process_slices(slices1,slices2)
        target = np.zeros_like(X)
        [p.dK_dX(partial[s1,s2],X[s1,i_s],X2[s2,i_s],target[s1,i_s]) for p,i_s,ps,s1,s2 in zip(self.parts,self.input_slices, self.param_slices,slices1,slices2)]
        return target

    def Kdiag(self,X,slices=None):
        assert X.shape[1]==self.D
        slices = self._process_slices(slices,False)
        target = np.zeros(X.shape[0])
        [p.Kdiag(X[s,i_s],target=target[s]) for p,i_s,s in zip(self.parts,self.input_slices,slices)]
        return target

    def dKdiag_dtheta(self,partial,X,slices=None):
        assert X.shape[1]==self.D
        assert len(partial.shape)==1
        assert partial.size==X.shape[0]
        slices = self._process_slices(slices,False)
        target = np.zeros(self.Nparam)
        [p.dKdiag_dtheta(partial[s],X[s,i_s],target[ps]) for p,i_s,s,ps in zip(self.parts,self.input_slices,slices,self.param_slices)]
        return target

    def dKdiag_dX(self, X, slices=None):
        assert X.shape[1]==self.D
        slices = self._process_slices(slices,False)
        target = np.zeros_like(X)
        [p.dKdiag_dX(partial[s],X[s,i_s],target[s,i_s]) for p,i_s,s in zip(self.parts,self.input_slices,slices)]
        return target

    def psi0(self,Z,mu,S,slices_mu=None,slices_Z=None):
        target = np.zeros(mu.shape[0])
        [p.psi0(Z,mu,S,target) for p in self.parts]
        return target

    def dpsi0_dtheta(self,Z,mu,S):
        target = np.zeros((mu.shape[0],self.Nparam))
        [p.dpsi0_dtheta(Z,mu,S,target[s]) for p,s in zip(self.parts, self.param_slices)]
        return target

    def dpsi0_dmuS(self,Z,mu,S):
        target_mu,target_S = np.zeros_like(mu),np.zeros_like(S)
        [p.dpsi0_dmuS(Z,mu,S,target_mu,target_S) for p in self.parts]
        return target_mu,target_S

    def psi1(self,Z,mu,S):
        """Think N,M,Q """
        target = np.zeros((mu.shape[0],Z.shape[0]))
        [p.psi1(Z,mu,S,target=target) for p in self.parts]
        return target

    def dpsi1_dtheta(self,Z,mu,S):
        """N,M,(Ntheta)"""
        target = np.zeros((mu.shape[0],Z.shape[0],self.Nparam))
        [p.dpsi1_dtheta(Z,mu,S,target[:,:,s]) for p,s in zip(self.parts, self.param_slices)]
        return target

    def dpsi1_dZ(self,Z,mu,S):
        """N,M,Q"""
        target = np.zeros((mu.shape[0],Z.shape[0],Z.shape[1]))
        [p.dpsi1_dZ(Z,mu,S,target) for p in self.parts]
        return target

    def dpsi1_dmuS(self,Z,mu,S):
        """return shapes are N,M,Q"""
        target_mu, target_S = np.zeros((2,mu.shape[0],Z.shape[0],Z.shape[1]))
        [p.dpsi1_dmuS(Z,mu,S,target_mu=target_mu,target_S = target_S) for p in self.parts]
        return target_mu, target_S

    def psi2(self,Z,mu,S):
        """
        :Z: np.ndarray of inducing inputs (M x Q)
        : mu, S: np.ndarrays of means and variacnes (each N x Q)
        :returns psi2: np.ndarray (N,M,M,Q) """
        target = np.zeros((mu.shape[0],Z.shape[0],Z.shape[0]))
        [p.psi2(Z,mu,S,target=target) for p in self.parts]
        return target

    def dpsi2_dtheta(self,Z,mu,S):
        """Returns shape (N,M,M,Ntheta)"""
        target = np.zeros((Z.shape[0],Z.shape[0],self.Nparam))
        [p.dpsi2_dtheta(Z,mu,S,target[:,:,s]) for p,s in zip(self.parts, self.param_slices)]
        return target

    def dpsi2_dZ(self,Z,mu,S):
        """N,M,M,Q"""
        target = np.zeros((mu.shape[0],Z.shape[0],Z.shape[0],Z.shape[1]))
        [p.dpsi2_dZ(Z,mu,S,target) for p in self.parts]
        return target

    def dpsi2_dmuS(self,Z,mu,S):
        """return shapes are N,M,M,Q"""
        target_mu, target_S = np.zeros((2,mu.shape[0],Z.shape[0],Z.shape[0],Z.shape[1]))
        [p.dpsi2_dmuS(Z,mu,S,target_mu=target_mu,target_S = target_S) for p in self.parts]

        #TODO: there are some extra terms to compute here!
        return target_mu, target_S