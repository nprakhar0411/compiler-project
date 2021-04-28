extern printf
section .text
	global main
fib:
	push ebp
	mov ebp, esp
	sub esp, 36
	mov eax, dword [ebp+8]
	mov ebx, eax
	cmp ebx, 0
	je __l5
	mov ebx, 0
	jmp __l6
__l5:
	mov ebx, 1
__l6:
	mov dword [ebp+8], eax
	mov dword [ebp-8], ebx
	cmp ebx, 0
	mov dword [ebp-4], eax
	je __l1
	mov dword [ebp-12], 1
	jmp __l0
__l1:
	mov eax, dword [ebp+8]
	cmp eax, 1
	je __l7
	mov eax, 0
	jmp __l8
__l7:
	mov eax, 1
__l8:
	mov dword [ebp-16], eax
	cmp eax, 0
	je __l2
	mov dword [ebp-12], 1
	jmp __l0
__l2:
	mov dword [ebp-12], 0
__l0:
	mov eax, dword [ebp-12]
	cmp eax, 0
	je __l3
	mov eax, dword [ebp+8]
	mov esp, ebp
	pop ebp
	ret
__l3:
	mov eax, dword [ebp+8]
	sub eax, 1
	push eax
	mov dword [ebp-20], eax
	call fib
	mov dword [ebp-24], eax
	add esp, 4
	mov eax, dword [ebp+8]
	sub eax, 2
	push eax
	mov dword [ebp-28], eax
	call fib
	mov dword [ebp-32], eax
	add esp, 4
	mov eax, dword [ebp-24]
	add eax, dword [ebp-32]
	mov dword [x_0], eax
	mov dword [ebp-36], eax
	mov esp, ebp
	pop ebp
	ret
main:
	push ebp
	mov ebp, esp
	sub esp, 20
	mov dword [ebp-4], 5
	mov dword [ebp-8], 7
	mov dword [ebp-12], 1
	push 7
	call fib
	mov dword [ebp-16], eax
	add esp, 4
	push dword [ebp-16]
	push __t_8
	call printf
	mov dword [ebp-20], eax
	add esp, 8
	mov eax, 1
	mov esp, ebp
	pop ebp
	ret
section	.data
	x_0	dd	0
	y_0	dd	0
	__t_8:	db	`%d\n`, 0
