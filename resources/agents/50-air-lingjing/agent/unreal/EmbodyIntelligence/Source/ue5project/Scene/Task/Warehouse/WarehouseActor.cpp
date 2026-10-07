#include "WarehouseActor.h"
#include "UObject/ConstructorHelpers.h"

AWarehouseActor::AWarehouseActor()
{
	MarkerMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MarkerMesh"));
	MarkerMesh->SetupAttachment(SceneComponent);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube"));
	if (CubeMesh.Succeeded())
	{
		MarkerMesh->SetStaticMesh(CubeMesh.Object);
	}

	MarkerMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MarkerMesh->SetRelativeScale3D(FVector(5.0f, 5.0f, 2.0f));
}

void AWarehouseActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	Super::InitTaskPoint(InTaskPointInfo);
	
	InitTagWidget(FSColor(255, 229, 0, 0.5f), TaskPointInfo.TaskPointId);
}
