/* Unix side of the MacX d3d12 wrapper: a single Wine unix call that writes a pointer into
 * read-only memory (D3DMetal's shared ID3D12CommandQueue vtable lives in a read-only Mach-O segment). */
#include <mach/mach.h>
#include <stdint.h>

struct write_ptr_params { void **slot; void *value; };

static int write_ptr(void *args)
{
    struct write_ptr_params *p = args;
    vm_address_t start = (vm_address_t)p->slot & ~(vm_address_t)(vm_page_size - 1);
    vm_size_t size = (((vm_address_t)(p->slot + 1) + vm_page_size - 1) & ~(vm_address_t)(vm_page_size - 1)) - start;
    if (vm_protect(mach_task_self(), start, size, 0, VM_PROT_READ | VM_PROT_WRITE | VM_PROT_COPY) != KERN_SUCCESS)
        return 0xc0000022; /* STATUS_ACCESS_DENIED */
    *p->slot = p->value;
    vm_protect(mach_task_self(), start, size, 0, VM_PROT_READ);
    return 0;
}

__attribute__((visibility("default"))) const void *__wine_unix_call_funcs[] = { (void *)write_ptr };
