#include "DeliveryActor.h"
#include "UObject/ConstructorHelpers.h"

ADeliveryActor::ADeliveryActor()
{
	MarkerMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MarkerMesh"));
	MarkerMesh->SetupAttachment(SceneComponent);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere"));
	if (SphereMesh.Succeeded())
	{
		MarkerMesh->SetStaticMesh(SphereMesh.Object);
	}

	MarkerMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MarkerMesh->SetRelativeScale3D(FVector(2.0f));
}

void ADeliveryActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	Super::InitTaskPoint(InTaskPointInfo);
	
	InitTagWidget(FSColor(255, 229, 0, 0.5f), TaskPointInfo.TaskPointId);
}


