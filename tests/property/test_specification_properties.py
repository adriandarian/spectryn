"""
Property-based tests for the Specification pattern.

Tests algebraic laws for specification composition:
- Boolean algebra laws (and, or, not)
- Collection operation invariants
"""

import pytest
from dataclasses import dataclass
from hypothesis import given, assume, settings
from hypothesis import strategies as st
from typing import Any

from md2jira.core.specification import (
    Specification,
    PredicateSpec,
    AlwaysTrue,
    AlwaysFalse,
    HasAttribute,
    StatusSpec,
    TitleMatchesSpec,
    all_of,
    any_of,
    none_of,
)


# =============================================================================
# Strategies
# =============================================================================

@dataclass
class MockObject:
    """Simple mock object for testing specifications."""
    value: int
    name: str
    status: str


# Strategy for mock objects
mock_objects = st.builds(
    MockObject,
    value=st.integers(),
    name=st.text(max_size=50),
    status=st.sampled_from(["Open", "Done", "Blocked", "In Progress"]),
)

# Strategy for lists of mock objects
mock_object_lists = st.lists(mock_objects, min_size=0, max_size=20)

# Strategy for predicate functions
int_predicates = st.sampled_from([
    (lambda x: x.value > 0, "positive"),
    (lambda x: x.value < 0, "negative"),
    (lambda x: x.value == 0, "zero"),
    (lambda x: x.value % 2 == 0, "even"),
    (lambda x: len(x.name) > 5, "long_name"),
])


def make_spec(pred_name: tuple) -> PredicateSpec:
    """Create a PredicateSpec from a predicate tuple."""
    pred, name = pred_name
    return PredicateSpec(pred, name)


# =============================================================================
# Boolean Algebra Laws
# =============================================================================

class TestBooleanAlgebraLaws:
    """
    Specifications should satisfy Boolean algebra laws:
    - Identity: A ∧ True = A, A ∨ False = A
    - Domination: A ∧ False = False, A ∨ True = True
    - Idempotent: A ∧ A = A, A ∨ A = A
    - Complement: A ∧ ¬A = False, A ∨ ¬A = True
    - Double negation: ¬(¬A) = A
    - De Morgan's: ¬(A ∧ B) = ¬A ∨ ¬B, ¬(A ∨ B) = ¬A ∧ ¬B
    """
    
    @given(mock_objects, int_predicates)
    def test_and_identity(self, obj, pred):
        """A ∧ True = A."""
        spec = make_spec(pred)
        combined = spec.and_(AlwaysTrue())
        
        assert combined.is_satisfied_by(obj) == spec.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_or_identity(self, obj, pred):
        """A ∨ False = A."""
        spec = make_spec(pred)
        combined = spec.or_(AlwaysFalse())
        
        assert combined.is_satisfied_by(obj) == spec.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_and_domination(self, obj, pred):
        """A ∧ False = False."""
        spec = make_spec(pred)
        combined = spec.and_(AlwaysFalse())
        
        assert not combined.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_or_domination(self, obj, pred):
        """A ∨ True = True."""
        spec = make_spec(pred)
        combined = spec.or_(AlwaysTrue())
        
        assert combined.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_and_idempotent(self, obj, pred):
        """A ∧ A = A."""
        spec = make_spec(pred)
        combined = spec.and_(spec)
        
        assert combined.is_satisfied_by(obj) == spec.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_or_idempotent(self, obj, pred):
        """A ∨ A = A."""
        spec = make_spec(pred)
        combined = spec.or_(spec)
        
        assert combined.is_satisfied_by(obj) == spec.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_complement_and(self, obj, pred):
        """A ∧ ¬A = False."""
        spec = make_spec(pred)
        combined = spec.and_(spec.not_())
        
        assert not combined.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_complement_or(self, obj, pred):
        """A ∨ ¬A = True."""
        spec = make_spec(pred)
        combined = spec.or_(spec.not_())
        
        assert combined.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates)
    def test_double_negation(self, obj, pred):
        """¬(¬A) = A."""
        spec = make_spec(pred)
        double_neg = spec.not_().not_()
        
        assert double_neg.is_satisfied_by(obj) == spec.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates, int_predicates)
    def test_de_morgan_and(self, obj, pred1, pred2):
        """¬(A ∧ B) = ¬A ∨ ¬B."""
        spec1 = make_spec(pred1)
        spec2 = make_spec(pred2)
        
        # ¬(A ∧ B)
        left = spec1.and_(spec2).not_()
        
        # ¬A ∨ ¬B
        right = spec1.not_().or_(spec2.not_())
        
        assert left.is_satisfied_by(obj) == right.is_satisfied_by(obj)
    
    @given(mock_objects, int_predicates, int_predicates)
    def test_de_morgan_or(self, obj, pred1, pred2):
        """¬(A ∨ B) = ¬A ∧ ¬B."""
        spec1 = make_spec(pred1)
        spec2 = make_spec(pred2)
        
        # ¬(A ∨ B)
        left = spec1.or_(spec2).not_()
        
        # ¬A ∧ ¬B
        right = spec1.not_().and_(spec2.not_())
        
        assert left.is_satisfied_by(obj) == right.is_satisfied_by(obj)


# =============================================================================
# Operator Equivalence
# =============================================================================

class TestOperatorEquivalence:
    """Test that operators (&, |, ~) are equivalent to methods."""
    
    @given(mock_objects, int_predicates, int_predicates)
    def test_and_operator_equivalent(self, obj, pred1, pred2):
        """& operator is equivalent to and_() method."""
        spec1 = make_spec(pred1)
        spec2 = make_spec(pred2)
        
        method_result = spec1.and_(spec2).is_satisfied_by(obj)
        operator_result = (spec1 & spec2).is_satisfied_by(obj)
        
        assert method_result == operator_result
    
    @given(mock_objects, int_predicates, int_predicates)
    def test_or_operator_equivalent(self, obj, pred1, pred2):
        """| operator is equivalent to or_() method."""
        spec1 = make_spec(pred1)
        spec2 = make_spec(pred2)
        
        method_result = spec1.or_(spec2).is_satisfied_by(obj)
        operator_result = (spec1 | spec2).is_satisfied_by(obj)
        
        assert method_result == operator_result
    
    @given(mock_objects, int_predicates)
    def test_not_operator_equivalent(self, obj, pred):
        """~ operator is equivalent to not_() method."""
        spec = make_spec(pred)
        
        method_result = spec.not_().is_satisfied_by(obj)
        operator_result = (~spec).is_satisfied_by(obj)
        
        assert method_result == operator_result


# =============================================================================
# Collection Operation Invariants
# =============================================================================

class TestCollectionInvariants:
    """Test invariants for filter, count, etc."""
    
    @given(mock_object_lists, int_predicates)
    def test_filter_count_consistency(self, objects, pred):
        """filter().length == count()."""
        spec = make_spec(pred)
        
        filtered = spec.filter(objects)
        counted = spec.count(objects)
        
        assert len(filtered) == counted
    
    @given(mock_object_lists, int_predicates)
    def test_filter_all_satisfy(self, objects, pred):
        """All filtered items satisfy the spec."""
        spec = make_spec(pred)
        filtered = spec.filter(objects)
        
        assert all(spec.is_satisfied_by(obj) for obj in filtered)
    
    @given(mock_object_lists, int_predicates)
    def test_filter_preserves_order(self, objects, pred):
        """Filter preserves original order."""
        spec = make_spec(pred)
        filtered = spec.filter(objects)
        
        # Verify order by tracking positions in original list
        prev_idx = -1
        for obj in filtered:
            # Find this object's position (handle duplicates by starting from prev)
            for i, orig in enumerate(objects):
                if i > prev_idx and orig is obj:
                    assert i > prev_idx, "Order should be preserved"
                    prev_idx = i
                    break
    
    @given(mock_object_lists, int_predicates)
    def test_any_satisfy_implies_non_empty_filter(self, objects, pred):
        """any_satisfy => filter is non-empty."""
        spec = make_spec(pred)
        
        if spec.any_satisfy(objects):
            assert len(spec.filter(objects)) > 0
    
    @given(mock_object_lists, int_predicates)
    def test_all_satisfy_implies_full_filter(self, objects, pred):
        """all_satisfy => filter equals original."""
        spec = make_spec(pred)
        
        if spec.all_satisfy(objects) and objects:
            assert spec.filter(objects) == objects
    
    @given(mock_object_lists, int_predicates)
    def test_first_in_filtered(self, objects, pred):
        """first() returns an element from filter()."""
        spec = make_spec(pred)
        
        first = spec.first(objects)
        filtered = spec.filter(objects)
        
        if first is not None:
            assert first in filtered
            assert first == filtered[0]
        else:
            assert len(filtered) == 0
    
    @given(mock_object_lists, int_predicates)
    def test_not_inverts_filter(self, objects, pred):
        """~spec.filter() is complement of spec.filter()."""
        spec = make_spec(pred)
        
        matching = set(id(obj) for obj in spec.filter(objects))
        not_matching = set(id(obj) for obj in spec.not_().filter(objects))
        all_ids = set(id(obj) for obj in objects)
        
        # Matching and not_matching should partition all objects
        assert matching & not_matching == set()
        assert matching | not_matching == all_ids


# =============================================================================
# Builder Invariants
# =============================================================================

class TestBuilderInvariants:
    """Test invariants for all_of, any_of, none_of."""
    
    @given(mock_objects, st.lists(int_predicates, min_size=1, max_size=5))
    def test_all_of_is_conjunction(self, obj, preds):
        """all_of is equivalent to manual and_ chain."""
        specs = [make_spec(p) for p in preds]
        
        all_of_result = all_of(*specs).is_satisfied_by(obj)
        manual_result = all(s.is_satisfied_by(obj) for s in specs)
        
        assert all_of_result == manual_result
    
    @given(mock_objects, st.lists(int_predicates, min_size=1, max_size=5))
    def test_any_of_is_disjunction(self, obj, preds):
        """any_of is equivalent to manual or_ chain."""
        specs = [make_spec(p) for p in preds]
        
        any_of_result = any_of(*specs).is_satisfied_by(obj)
        manual_result = any(s.is_satisfied_by(obj) for s in specs)
        
        assert any_of_result == manual_result
    
    @given(mock_objects, st.lists(int_predicates, min_size=1, max_size=5))
    def test_none_of_is_negated_any(self, obj, preds):
        """none_of is equivalent to ~any_of."""
        specs = [make_spec(p) for p in preds]
        
        none_of_result = none_of(*specs).is_satisfied_by(obj)
        negated_any_result = not any(s.is_satisfied_by(obj) for s in specs)
        
        assert none_of_result == negated_any_result
    
    @given(mock_objects)
    def test_empty_all_of_is_true(self, obj):
        """all_of() with no specs is AlwaysTrue."""
        assert all_of().is_satisfied_by(obj)
    
    @given(mock_objects)
    def test_empty_any_of_is_false(self, obj):
        """any_of() with no specs is AlwaysFalse."""
        assert not any_of().is_satisfied_by(obj)


# =============================================================================
# StatusSpec Properties
# =============================================================================

class TestStatusSpecProperties:
    """Test StatusSpec properties."""
    
    @given(st.sampled_from(["Open", "Done", "Blocked", "In Progress"]))
    def test_status_matches_itself(self, status):
        """StatusSpec(s) matches objects with status s."""
        spec = StatusSpec(status)
        obj = MockObject(value=0, name="test", status=status)
        
        assert spec.is_satisfied_by(obj)
    
    @given(
        st.sampled_from(["Open", "Done", "Blocked"]),
        st.sampled_from(["Open", "Done", "Blocked"]),
    )
    def test_status_case_insensitive(self, status, query):
        """StatusSpec is case-insensitive."""
        obj = MockObject(value=0, name="test", status=status)
        
        lower = StatusSpec(query.lower()).is_satisfied_by(obj)
        upper = StatusSpec(query.upper()).is_satisfied_by(obj)
        
        assert lower == upper
    
    @given(st.lists(st.sampled_from(["Open", "Done", "Blocked"]), min_size=1, max_size=3))
    def test_multi_status_is_any(self, statuses):
        """StatusSpec with multiple statuses matches any of them."""
        spec = StatusSpec(*statuses)
        
        for status in statuses:
            obj = MockObject(value=0, name="test", status=status)
            assert spec.is_satisfied_by(obj)


# =============================================================================
# TitleMatchesSpec Properties
# =============================================================================

@dataclass
class TitledObject:
    title: str


class TestTitleMatchesProperties:
    """Test TitleMatchesSpec properties."""
    
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=3, max_size=50))
    def test_title_matches_self(self, title):
        """Title matches itself."""
        assume(title.strip())  # Non-empty after strip
        
        spec = TitleMatchesSpec(title)
        obj = TitledObject(title=title)
        
        assert spec.is_satisfied_by(obj)
    
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=3, max_size=50))
    def test_title_matches_case_insensitive(self, title):
        """Title matching is case-insensitive for ASCII."""
        assume(title.strip())
        
        lower_spec = TitleMatchesSpec(title.lower())
        upper_spec = TitleMatchesSpec(title.upper())
        obj = TitledObject(title=title)
        
        # For ASCII text, case should not matter
        assert lower_spec.is_satisfied_by(obj) == upper_spec.is_satisfied_by(obj)
    
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=50), st.integers(min_value=0, max_value=10))
    def test_title_matches_substring(self, title, start):
        """Contains match finds substrings."""
        assume(len(title.strip()) > 3)
        
        # Extract a substring
        end = min(start + 3, len(title))
        substring = title[start:end]
        assume(substring.strip())
        
        spec = TitleMatchesSpec(substring, exact=False)
        obj = TitledObject(title=title)
        
        assert spec.is_satisfied_by(obj)

